import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import get_db
from app.models import Audit, LocalCredential, User
from app.config import settings
from app.passwords import hash_password
from test_sqlserver_integration import environment, login  # noqa: F401

pytestmark = pytest.mark.sqlserver


def test_admin_people_management_permissions_sessions_and_audit(environment, monkeypatch):  # noqa: F811
    ids, _ = environment
    factory = app.dependency_overrides[get_db]
    gen = factory()
    db = next(gen)
    admin = User(subject=uuid.uuid4().hex, name="Admin", role="System Admin", org_id=db.get(User, ids[0]).org_id, active=True)
    db.add(admin)
    db.flush()
    admin_id, org_id = admin.id, admin.org_id
    db.add(LocalCredential(user_id=admin.id, username="admin-" + uuid.uuid4().hex, password_hash=hash_password("Admin-initial-password")))
    try:
        next(gen)
    except StopIteration:
        pass
    actor, employee = TestClient(app), TestClient(app)
    login(actor, admin_id)
    login(employee, ids[0])
    username = "user-" + uuid.uuid4().hex
    first_password, second_password = "First-password-123", "Second-password-456"
    body = {"name": "Managed user", "username": username, "password": first_password, "org_id": org_id, "role": "Employee"}
    assert employee.get("/api/v1/admin/people").status_code == 403
    assert employee.get("/api/v1/admin/people/options").status_code == 403
    assert employee.post("/api/v1/admin/people", json=body).status_code == 403
    created = actor.post("/api/v1/admin/people", json=body)
    assert created.status_code == 201, created.text
    person = created.json()
    assert "password" not in created.text and first_password not in created.text
    assert actor.post("/api/v1/admin/people", json={**body, "username": username.upper()}).status_code == 409
    assert actor.post("/api/v1/admin/people", json={**body, "username": username + "x", "role": "Root"}).status_code == 422
    base = f"/api/v1/admin/people/{person['id']}"
    profile = {"name": "Managed user", "org_id": org_id, "role": "Manager"}
    for path, payload, method in [
        (base, profile, "patch"),
        (base + "/active", {"active": False}, "post"),
        (base + "/password", {"password": second_password}, "post"),
    ]:
        assert getattr(employee, method)(path, json=payload, headers={"If-Match": person["etag"]}).status_code == 403
    assert actor.patch(base, json=profile).status_code == 428
    updated = actor.patch(base, json=profile, headers={"If-Match": person["etag"]})
    assert updated.status_code == 200
    assert actor.patch(base, json=profile, headers={"If-Match": person["etag"]}).status_code == 412
    person = updated.json()
    mine = next(p for p in actor.get("/api/v1/admin/people?q=Admin").json()["items"] if p["id"] == admin_id)
    assert actor.post(f"/api/v1/admin/people/{admin_id}/active", json={"active": False}, headers={"If-Match": mine["etag"]}).status_code == 409
    assert (
        actor.patch(
            f"/api/v1/admin/people/{admin_id}", json={"name": "Admin", "org_id": org_id, "role": "Employee"}, headers={"If-Match": mine["etag"]}
        ).status_code
        == 409
    )
    monkeypatch.setenv("OKR_AUTH_MODE", "password")
    settings.cache_clear()
    target = TestClient(app)
    target.headers["Origin"] = settings().public_url.rstrip("/")

    def authenticate(password):
        return target.post("/auth/password/login", json={"username": username, "password": password})

    assert authenticate(first_password).status_code == 200
    assert actor.post(base + "/password", json={"password": second_password}, headers={"If-Match": person["etag"]}).status_code == 200
    assert target.get("/api/v1/me").status_code == 401
    assert authenticate(first_password).status_code == 401
    assert authenticate(second_password).status_code == 200
    role_change = actor.patch(base, json={**profile, "role": "Audit"}, headers={"If-Match": person["etag"]})
    assert role_change.status_code == 200
    person = role_change.json()
    assert target.get("/api/v1/me").status_code == 401
    assert authenticate(second_password).status_code == 200
    disabled = actor.post(base + "/active", json={"active": False}, headers={"If-Match": person["etag"]})
    assert disabled.status_code == 200
    assert target.get("/api/v1/me").status_code == 401
    assert authenticate(second_password).status_code == 401
    enabled = actor.post(base + "/active", json={"active": True}, headers={"If-Match": disabled.json()["etag"]})
    assert enabled.status_code == 200
    assert authenticate(second_password).status_code == 200
    # Self password resets also revoke the acting administrator's session.
    current_admin = next(p for p in actor.get("/api/v1/admin/people?q=Admin").json()["items"] if p["id"] == admin_id)
    assert (
        actor.post(
            f"/api/v1/admin/people/{admin_id}/password", json={"password": "Admin-replacement-password"}, headers={"If-Match": current_admin["etag"]}
        ).status_code
        == 200
    )
    assert actor.get("/api/v1/me").status_code == 401
    gen = factory()
    db = next(gen)
    credential = db.get(LocalCredential, person["id"])
    assert first_password not in credential.password_hash and second_password not in credential.password_hash
    events = list(db.scalars(select(Audit).where(Audit.actor_id == admin_id)))
    for event in events:
        assert first_password not in event.detail and second_password not in event.detail
        assert "password_hash" not in event.detail
    assert {"CreatePerson", "EditPerson", "ResetPersonPassword", "DisablePerson", "EnablePerson"} <= {e.action for e in events}
    assert any(json.loads(e.detail).get("person_id") == person["id"] for e in events)
    gen.close()
