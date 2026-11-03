"""Administrator-only identity management; credentials never appear in audit payloads."""

import hashlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import delete, func, or_, select, true
from sqlalchemy.orm import Session

from .admin import require_admin
from .db import get_db
from .models import AppSession, LocalCredential, LoginAttempt, OrgUnit, User
from .passwords import hash_password, normalize_username
from .schemas import Input
from .security import current_user, digest
from .services import audit, lock

router = APIRouter(prefix="/api/v1/admin", tags=["people"])
Role = Literal["Employee", "Manager", "Division Head", "PMO", "HR", "System Admin", "Audit"]


class Profile(Input):
    name: str = Field(min_length=1, max_length=100)
    org_id: int
    role: Role


class CreatePerson(Profile):
    username: str = Field(min_length=3, max_length=64)
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def username_valid(cls, value):
        return normalize_username(value)


class SetActive(Input):
    active: bool


class ResetPassword(Input):
    password: SecretStr = Field(min_length=12, max_length=128)


def person_view(db, person):
    credential = db.get(LocalCredential, person.id)
    public = {
        "id": person.id,
        "name": person.name,
        "org_id": person.org_id,
        "role": person.role,
        "active": person.active,
        "username": credential.username if credential else None,
        "org_name": db.get(OrgUnit, person.org_id).name,
    }
    public["etag"] = '"' + hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest() + '"'
    return public


def admin_write(db, user):
    # Recheck the acting administrator under a shared mutation lock: concurrent
    # administrators cannot disable/demote one another using stale permissions.
    lock(db, "people-admin")
    db.refresh(user)
    require_admin(user)
    if not user.active:
        raise HTTPException(403)


def target_person(db, person_id, request):
    person = db.get(User, person_id)
    if not person:
        raise HTTPException(404)
    before = person_view(db, person)
    if not request.headers.get("if-match"):
        raise HTTPException(428, "请提供If-Match版本")
    if request.headers["if-match"] != before["etag"]:
        raise HTTPException(412, "数据已被修改，请刷新后重试")
    return person, before


def revoke_sessions(db, person):
    db.execute(delete(AppSession).where(AppSession.user_id == person.id))


def guard_admin(db, actor, person, role, active):
    if actor.id == person.id and (role != "System Admin" or not active):
        raise HTTPException(409, "不能停用自己或撤销自己的管理员角色")
    if person.active and person.role == "System Admin" and (role != "System Admin" or not active):
        count = db.scalar(select(func.count()).select_from(User).where(User.active == true(), User.role == "System Admin"))
        if count <= 1:
            raise HTTPException(409, "必须保留至少一名启用的系统管理员")


@router.get("/people/options")
def options(user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    require_admin(user)
    return {
        "organizations": [{"id": o.id, "name": o.name} for o in db.scalars(select(OrgUnit).order_by(OrgUnit.id))],
        "roles": ["Employee", "Manager", "Division Head", "PMO", "HR", "System Admin", "Audit"],
    }


@router.get("/people")
def people(
    q: str = Query("", max_length=100),
    active: bool | None = None,
    page: int = Query(1, ge=1),
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    require_admin(user)
    query = select(User)
    if q:
        usernames = select(LocalCredential.user_id).where(LocalCredential.username.contains(q, autoescape=True))
        query = query.where(or_(User.name.contains(q, autoescape=True), User.id.in_(usernames)))
    if active is not None:
        query = query.where(User.active == active)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {"items": [person_view(db, p) for p in db.scalars(query.order_by(User.id).offset((page - 1) * 20).limit(20))], "total": total}


@router.post("/people", status_code=201)
def create(body: CreatePerson, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    admin_write(db, user)
    if not db.get(OrgUnit, body.org_id):
        raise HTTPException(422, "组织不存在")
    lock(db, "password:" + digest("account:" + body.username))
    if db.scalar(select(LocalCredential.user_id).where(LocalCredential.username == body.username)):
        raise HTTPException(409, "账号已存在")
    person = User(subject="local:" + uuid.uuid4().hex, **body.model_dump(exclude={"username", "password"}), active=True)
    db.add(person)
    db.flush()
    db.add(LocalCredential(user_id=person.id, username=body.username, password_hash=hash_password(body.password.get_secret_value())))
    db.flush()
    audit(
        db,
        user,
        request,
        "CreatePerson",
        None,
        {"person_id": person.id, "name": person.name, "username": body.username, "org_id": person.org_id, "role": person.role},
    )
    return person_view(db, person)


@router.patch("/people/{person_id}")
def edit(
    person_id: int, body: Profile, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    admin_write(db, user)
    person, before = target_person(db, person_id, request)
    guard_admin(db, user, person, body.role, person.active)
    if not db.get(OrgUnit, body.org_id):
        raise HTTPException(422, "组织不存在")
    for key, value in body.model_dump().items():
        setattr(person, key, value)
    revoke_sessions(db, person)
    audit(db, user, request, "EditPerson", None, {"person_id": person.id, "before": before, "after": body.model_dump()})
    db.flush()
    return person_view(db, person)


@router.post("/people/{person_id}/active")
def set_active(
    person_id: int, body: SetActive, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    admin_write(db, user)
    person, before = target_person(db, person_id, request)
    guard_admin(db, user, person, person.role, body.active)
    person.active = body.active
    revoke_sessions(db, person)
    audit(db, user, request, "EnablePerson" if body.active else "DisablePerson", None, {"person_id": person.id, "previous_active": before["active"]})
    db.flush()
    return person_view(db, person)


@router.post("/people/{person_id}/password")
def reset_password(
    person_id: int, body: ResetPassword, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    admin_write(db, user)
    person, _ = target_person(db, person_id, request)
    credential = db.get(LocalCredential, person.id)
    if not credential:
        raise HTTPException(409, "此人员尚无本地登录账号")
    lock(db, "password:" + digest("account:" + credential.username))
    credential.password_hash = hash_password(body.password.get_secret_value())
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == digest("account:" + credential.username)))
    revoke_sessions(db, person)
    audit(db, user, request, "ResetPersonPassword", None, {"person_id": person.id})
    return {"ok": True}
