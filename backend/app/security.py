from sqlalchemy import true
import hashlib
import hmac
import json
import secrets
from datetime import timedelta

import msal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AppSession, LoginFlow, LocalCredential, LoginAttempt, ObjectiveGrant, OrgUnit, User, now
from .passwords import DUMMY_HASH, normalize_username, verify_password

router = APIRouter(prefix="/auth", tags=["identity"])


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def current_user(request: Request, db: Session = Depends(get_db, scope="function")):
    token = request.cookies.get("okr_session", "")
    session = db.get(AppSession, digest(token)) if token else None
    if not session or session.expires_at < now() or session.last_seen < now() - timedelta(minutes=30):
        raise HTTPException(401, "登录已过期")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "用户已停用")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
            raise HTTPException(403, "CSRF校验失败")
    session.last_seen = now()
    request.state.session = session
    return user


def scope_ids(db, user):
    if user.role in ("PMO", "Audit"):
        return set(db.scalars(select(OrgUnit.id)))
    result = {user.org_id}
    if user.role in ("Manager", "Division Head"):
        units = db.scalars(select(OrgUnit)).all()
        while True:
            expanded = result | {u.id for u in units if u.parent_id in result}
            if expanded == result:
                break
            result = expanded
    return result


def can_read(db, user, objective):
    if user.role == "System Admin":
        return False
    if objective.owner_id == user.id:
        return True
    if db is not None and db.get(ObjectiveGrant, (objective.id, user.id)) is not None:
        return True
    if user.role == "Employee" or getattr(objective, "visibility", "organization") == "restricted":
        return False
    return objective.org_id in scope_ids(db, user)


def require_owner(user, objective):
    if objective.owner_id != user.id:
        raise HTTPException(403, "仅目标负责人可执行此操作")


def create_session(db, user, response):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(AppSession(token_hash=digest(token), user_id=user.id, csrf=csrf, expires_at=now() + timedelta(hours=8)))
    response.set_cookie("okr_session", token, httponly=True, secure=settings().public_url.startswith("https://"), samesite="lax", max_age=28800, path="/")


def oidc_client():
    cfg = settings()
    if not all((cfg.tenant_id, cfg.client_id, cfg.client_secret)):
        raise HTTPException(503, "尚未配置企业身份服务")
    return msal.ConfidentialClientApplication(
        cfg.client_id, authority=f"https://login.microsoftonline.com/{cfg.tenant_id}", client_credential=cfg.client_secret
    )


@router.get("/login")
def login(db: Session = Depends(get_db, scope="function")):
    if settings().auth_mode != "entra":
        raise HTTPException(404)
    flow = oidc_client().initiate_auth_code_flow(scopes=[], redirect_uri=settings().public_url.rstrip("/") + "/auth/callback")
    token = secrets.token_urlsafe(32)
    db.add(LoginFlow(token_hash=digest(token), payload=json.dumps(flow), expires_at=now() + timedelta(minutes=10)))
    response = RedirectResponse(flow["auth_uri"])
    response.set_cookie("okr_login", token, httponly=True, secure=settings().public_url.startswith("https://"), samesite="lax", max_age=600)
    return response


@router.get("/callback")
def callback(request: Request, db: Session = Depends(get_db, scope="function")):
    if settings().auth_mode != "entra":
        raise HTTPException(404)
    from .services import lock

    lock(db, "login:" + digest(request.cookies.get("okr_login", "")))
    flow = db.get(LoginFlow, digest(request.cookies.get("okr_login", "")))
    if not flow or flow.expires_at < now():
        raise HTTPException(401, "登录请求已失效")
    try:
        result = oidc_client().acquire_token_by_auth_code_flow(json.loads(flow.payload), dict(request.query_params))
    except ValueError:
        raise HTTPException(401, "身份回调校验失败") from None
    claims = result.get("id_token_claims", {})
    if claims.get("tid") != settings().tenant_id or not claims.get("oid"):
        raise HTTPException(401, "企业身份校验失败")
    user = db.scalar(select(User).where(User.subject == f"{claims['tid']}:{claims['oid']}", User.active == true()))
    if not user:
        raise HTTPException(403, "请联系管理员开通组织及角色授权")
    db.delete(flow)
    response = RedirectResponse("/")
    response.delete_cookie("okr_login")
    create_session(db, user, response)
    return response


class DevLogin(BaseModel):
    user_id: int


@router.get("/config")
def auth_config():
    return {
        "password_login": settings().auth_mode == "password",
        "development_login": settings().env != "production" and settings().auth_mode == "development" and settings().enable_dev_login,
    }


class PasswordLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=128)


@router.post("/password/login")
def password_login(body: PasswordLogin, request: Request, db: Session = Depends(get_db, scope="function")):
    from fastapi.responses import JSONResponse
    from .services import lock, audit

    if settings().auth_mode != "password":
        raise HTTPException(404)
    if request.headers.get("origin") != settings().public_url.rstrip("/"):
        raise HTTPException(403, "拒绝跨站登录")
    username = body.username.strip().lower()
    keys = [(digest("account:" + username), 5), (digest("ip:" + request.client.host), 30)]
    attempts = []
    for key, limit in sorted(keys):
        lock(db, "password:" + key)
        attempt = db.get(LoginAttempt, key)
        if attempt is None:
            attempt = LoginAttempt(key=key, failures=0, window_start=now())
            db.add(attempt)
        if attempt.window_start < now() - timedelta(minutes=15):
            attempt.failures, attempt.window_start = 0, now()
        if attempt.failures >= limit:
            return JSONResponse({"message": "登录尝试过多，请 15 分钟后重试"}, status_code=429, headers={"Retry-After": "900"})
        attempts.append(attempt)
    try:
        username = normalize_username(username)
    except ValueError:
        username = ""
    credential = db.scalar(select(LocalCredential).where(LocalCredential.username == username))
    valid = verify_password(body.password.get_secret_value(), credential.password_hash if credential else DUMMY_HASH)
    user = db.get(User, credential.user_id) if credential else None
    if not valid or not user or not user.active:
        for attempt in attempts:
            attempt.failures += 1
        # Return a response, so the failed-attempt transaction is committed.
        return JSONResponse({"message": "账号或密码错误"}, status_code=401)
    for attempt in attempts:
        if attempt.key == digest("account:" + username):
            attempt.failures = 0
    old = db.get(AppSession, digest(request.cookies.get("okr_session", "")))
    if old:
        db.delete(old)
    response = JSONResponse({"ok": True})
    create_session(db, user, response)
    audit(db, user, request, "password_login", None, {})
    return response


def require_dev(request):
    cfg = settings()
    if cfg.env == "production" or cfg.auth_mode != "development" or not cfg.enable_dev_login:
        raise HTTPException(404)
    origin = request.headers.get("origin")
    if origin and origin != cfg.public_url.rstrip("/"):
        raise HTTPException(403, "拒绝跨站开发登录")


@router.get("/development/users")
def dev_users(request: Request, db: Session = Depends(get_db, scope="function")):
    require_dev(request)
    return [{"id": u.id, "name": u.name, "role": u.role} for u in db.scalars(select(User).where(User.active == true()))]


@router.post("/development/login")
def dev_login(body: DevLogin, request: Request, db: Session = Depends(get_db, scope="function")):
    from fastapi.responses import JSONResponse

    require_dev(request)
    user = db.get(User, body.user_id)
    if not user or not user.active:
        raise HTTPException(401)
    response = JSONResponse({"ok": True})
    create_session(db, user, response)
    return response


@router.post("/logout")
def logout(request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    from fastapi.responses import JSONResponse

    db.delete(request.state.session)
    response = JSONResponse({"ok": True})
    response.delete_cookie("okr_session")
    return response
