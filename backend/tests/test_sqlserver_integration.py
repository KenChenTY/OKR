"""Run only against an explicitly supplied, migrated, disposable *_test database."""

import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import Cycle, OrgUnit, User

pytestmark = pytest.mark.sqlserver


@pytest.fixture
def environment(monkeypatch, tmp_path):
    url = os.environ.get("OKR_TEST_DATABASE_URL")
    if not url:
        pytest.skip("SQL Server not configured; set OKR_TEST_DATABASE_URL to a migrated *_test database")
    if not (make_url(url).database or "").lower().endswith("_test"):
        pytest.fail("Integration tests require a database name ending in _test")
    monkeypatch.setenv("OKR_ENV", "test")
    monkeypatch.setenv("OKR_AUTH_MODE", "development")
    monkeypatch.setenv("OKR_ENABLE_DEV_LOGIN", "true")
    monkeypatch.setenv("OKR_STORAGE_ROOT", str(tmp_path))
    settings.cache_clear()
    test_engine = create_engine(url, pool_pre_ping=True)
    factory = sessionmaker(test_engine, expire_on_commit=False)
    with factory() as db, db.begin():
        suffix = uuid.uuid4().hex[:8]
        parent = OrgUnit(name="Division " + suffix, unit_type="division")
        db.add(parent)
        db.flush()
        child = OrgUnit(name="Dept " + suffix, parent_id=parent.id, unit_type="department")
        db.add(child)
        db.flush()
        users = [
            User(subject=suffix + ":" + role, name=role, role=role, org_id=parent.id if role == "Division Head" else child.id)
            for role in ("Employee", "Manager", "Division Head")
        ]
        outsider = User(subject=suffix + ":outsider", name="outsider", role="Employee", org_id=child.id)
        cycle = Cycle(name="Test " + suffix, start_date=date.today() - timedelta(days=30), end_date=date.today() + timedelta(days=60))
        db.add_all([*users, outsider, cycle])
        db.flush()
        ids = [u.id for u in users] + [outsider.id]
        cycle_id = cycle.id

    def test_db():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = test_db
    try:
        yield ids, cycle_id
    finally:
        app.dependency_overrides.clear()
        settings.cache_clear()
        test_engine.dispose()


def login(client, uid):
    assert client.post("/auth/development/login", json={"user_id": uid}).status_code == 200
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]


def test_password_login_logout_lockout_and_disabled_user(environment, monkeypatch):
    from app.models import LocalCredential
    from app.passwords import hash_password

    ids, _ = environment
    username = "test-" + uuid.uuid4().hex
    password = "Integration-password-123"
    factory = app.dependency_overrides[get_db]
    gen = factory()
    db = next(gen)
    db.add(LocalCredential(user_id=ids[0], username=username, password_hash=hash_password(password)))
    try:
        next(gen)
    except StopIteration:
        pass
    monkeypatch.setenv("OKR_AUTH_MODE", "password")
    settings.cache_clear()
    client = TestClient(app)
    origin = settings().public_url.rstrip("/")
    payload = {"username": username, "password": password}
    assert client.post("/auth/password/login", json=payload).status_code == 403
    client.headers["Origin"] = origin
    assert client.post("/auth/development/login", json={"user_id": ids[0]}).status_code == 404
    assert client.post("/auth/password/login", json={**payload, "password": "wrong"}).status_code == 401
    result = client.post("/auth/password/login", json=payload)
    assert result.status_code == 200
    assert "httponly" in result.headers["set-cookie"].lower()
    me = client.get("/api/v1/me")
    assert me.json()["id"] == ids[0]
    assert client.post("/auth/logout").status_code == 403
    assert client.post("/auth/logout", headers={"X-CSRF-Token": me.json()["csrf"]}).status_code == 200
    assert client.get("/api/v1/me").status_code == 401
    for _ in range(5):
        assert client.post("/auth/password/login", json={**payload, "password": "wrong"}).status_code == 401
    assert client.post("/auth/password/login", json=payload).status_code == 429
    gen = factory()
    db = next(gen)
    db.get(User, ids[0]).active = False
    from app.models import LoginAttempt
    from app.security import digest

    db.get(LoginAttempt, digest("account:" + username)).failures = 0
    try:
        next(gen)
    except StopIteration:
        pass
    assert client.post("/auth/password/login", json=payload).status_code == 401


def test_full_approval_checkin_and_permission_boundary(environment):
    ids, cycle = environment
    employee, manager, division, outsider = [TestClient(app) for _ in range(4)]
    for client, uid in zip((employee, manager, division, outsider), ids):
        login(client, uid)
    created = employee.post(
        "/api/v1/objectives",
        json={
            "title": "Integration test",
            "description": "Real SQL Server transaction test",
            "cycle_id": cycle,
            "theme": "Test",
            "start_date": str(date.today() - timedelta(days=1)),
            "end_date": str(date.today() + timedelta(days=30)),
        },
    )
    assert created.status_code == 201, created.text
    obj = created.json()
    path = f"/api/v1/objectives/{obj['id']}"
    assert outsider.get(path).status_code == 404
    response = employee.post(
        path + "/key-results", headers={"If-Match": obj["etag"]}, json={"name": "Saved hours", "baseline": "0", "target": "100", "unit": "h", "weight": "100"}
    )
    assert response.status_code == 201, response.text
    obj = employee.get(path).json()
    draft_kr = obj["key_results"][0]
    updated_source = employee.patch(
        f"/api/v1/key-results/{draft_kr['id']}/evidence-source", headers={"If-Match": draft_kr["etag"]}, json={"evidence_source": "Monthly operations report"}
    )
    assert updated_source.status_code == 200, updated_source.text
    assert updated_source.json()["evidence_source"] == "Monthly operations report"
    assert (
        employee.patch(
            f"/api/v1/key-results/{draft_kr['id']}/evidence-source", headers={"If-Match": draft_kr["etag"]}, json={"evidence_source": "Stale write"}
        ).status_code
        == 412
    )
    obj = employee.get(path).json()
    stale = obj["etag"]
    response = employee.post(path + "/submit", headers={"If-Match": stale, "Idempotency-Key": "submit-once"})
    assert response.status_code == 200, response.text
    assert employee.post(path + "/submit", headers={"If-Match": stale, "Idempotency-Key": "submit-once"}).json() == response.json()
    for client in (manager, division):
        tasks = client.get("/api/v1/approvals").json()
        task = next(t for t in tasks if t["objective"]["id"] == obj["id"])
        result = client.post(
            f"/api/v1/workflow-tasks/{task['id']}/decisions",
            headers={"If-Match": task["objective"]["etag"], "Idempotency-Key": uuid.uuid4().hex},
            json={"decision": "Approved", "comment": "Verified"},
        )
        assert result.status_code == 200, result.text
    obj = employee.get(path).json()
    assert obj["status"] == "Approved"
    assert employee.post(path + "/transitions", headers={"If-Match": stale}, json={"action": "activate", "reason": "start"}).status_code == 412
    result = employee.post(path + "/transitions", headers={"If-Match": obj["etag"]}, json={"action": "activate", "reason": "start"})
    assert result.status_code == 200, result.text
    kr = result.json()["key_results"][0]
    assert employee.put(path + "/strategic-assessment", json={"score": 90, "rationale": "Not allowed"}).status_code == 403
    assert manager.put(path + "/strategic-assessment", json={"score": 80, "rationale": "Strategic efficiency priority"}).status_code == 200
    plan_body = {"objective_id": obj["id"], "reviewer_id": ids[1], "due_date": str(date.today() - timedelta(days=1))}
    assert employee.post("/api/v1/quarterly-reviews", json=plan_body).status_code == 403
    assert manager.post("/api/v1/quarterly-reviews", json={**plan_body, "reviewer_id": ids[0]}).status_code == 422
    planned = manager.post("/api/v1/quarterly-reviews", json=plan_body)
    assert planned.status_code == 201, planned.text
    analytics = manager.get(f"/api/v1/dashboards/organization?cycle_id={cycle}").json()
    assert analytics["strategic_value"] == "80.00"
    assert analytics["departments"][0]["overdue_reviews"] == 1
    assert outsider.get(f"/api/v1/dashboards/organization?cycle_id={cycle}").json()["departments"] == []
    complete_path = f"/api/v1/quarterly-reviews/{planned.json()['id']}/complete"
    conclusion = {"summary": "Progress reviewed", "lessons": "Measure evidence", "next_steps": "Continue improvement"}
    assert employee.post(complete_path, json=conclusion).status_code == 403
    assert manager.post(complete_path, json=conclusion).status_code == 200
    assert manager.post(complete_path, json=conclusion).status_code == 409
    assert manager.get(f"/api/v1/dashboards/organization?cycle_id={cycle}").json()["departments"][0]["overdue_reviews"] == 0
    payload = {"current_value": "50", "confidence": 80, "commentary": "Measured", "effective_at": datetime.now(timezone.utc).isoformat()}
    headers = {"If-Match": kr["etag"], "Idempotency-Key": "check-once"}
    result = employee.post(f"/api/v1/key-results/{kr['id']}/check-ins", headers=headers, json=payload)
    assert result.status_code == 201, result.text
    assert result.json()["progress"] == "50.00"
    assert employee.post(f"/api/v1/key-results/{kr['id']}/check-ins", headers=headers, json=payload).json() == result.json()
    assert outsider.get(f"/api/v1/key-results/{kr['id']}/check-ins").status_code == 404
    evidence = employee.post(
        "/api/v1/evidence/links", json={"objective_id": obj["id"], "name": "Evidence source", "url": "https://app.powerbi.com/groups/test"}
    )
    assert evidence.status_code == 201, evidence.text
    upload = employee.post(
        "/api/v1/evidence/uploads", data={"objective_id": obj["id"]}, files={"file": ("proof.pdf", b"%PDF-1.7\nquarantined fixture", "application/pdf")}
    )
    assert upload.status_code == 201, upload.text
    assert employee.get(f"/api/v1/evidence/versions/{upload.json()['id']}/download").status_code == 409
    assert outsider.get(f"/api/v1/evidence/versions/{upload.json()['id']}/download").status_code == 404
    benefit = employee.post(
        "/api/v1/benefits",
        json={
            "objective_id": obj["id"],
            "reference": uuid.uuid4().hex,
            "name": "Cost saving",
            "kr_id": kr["id"],
            "category": "cost_saving",
            "unit": "CNY",
            "currency": "CNY",
            "period_start": str(date.today()),
            "period_end": str(date.today() + timedelta(days=30)),
            "method": "Verified baseline difference",
        },
    )
    assert benefit.status_code == 201, benefit.text
    assert benefit.json()["kr_id"] == kr["id"]
    invalid_benefit = {
        "objective_id": obj["id"],
        "kr_id": -1,
        "reference": uuid.uuid4().hex,
        "name": "Invalid KR",
        "category": "hours_saved",
        "unit": "h",
        "period_start": str(date.today()),
        "period_end": str(date.today()),
        "method": "Test",
    }
    assert employee.post("/api/v1/benefits", json=invalid_benefit).status_code == 422
    claim = employee.post(
        f"/api/v1/benefits/{benefit.json()['id']}/claims",
        json={"claimed_value": "100", "narrative": "Claim with evidence", "evidence_id": evidence.json()["id"]},
    )
    assert claim.status_code == 201, claim.text
    verify_path = f"/api/v1/benefit-claims/{claim.json()['id']}/verifications"
    verify_body = {"decision": "Approved", "verified_value": "80", "comment": "Independent review"}
    assert employee.post(verify_path, json=verify_body).status_code == 403
    assert manager.post(verify_path, json=verify_body).status_code == 201
    assert manager.post(verify_path, json=verify_body).status_code == 409
    portfolio = manager.get(f"/api/v1/dashboards/portfolio?cycle_id={cycle}").json()
    assert any(x["category"] == "cost_saving" and float(x["value"]) == 80 for x in portfolio["verified_benefits"])
    assert outsider.get("/api/v1/benefits").json() == []
    obj = employee.get(path).json()
    assert manager.post(path + "/transitions", headers={"If-Match": obj["etag"]}, json={"action": "complete", "reason": "Without request"}).status_code == 409
    requested = employee.post(path + "/transitions", headers={"If-Match": obj["etag"]}, json={"action": "request_completion", "reason": "Ready for closure"})
    assert requested.status_code == 200, requested.text
    task = next(t for t in manager.get("/api/v1/approvals").json() if t["objective"]["id"] == obj["id"])
    completed = manager.post(
        f"/api/v1/workflow-tasks/{task['id']}/decisions",
        headers={"If-Match": task["objective"]["etag"], "Idempotency-Key": uuid.uuid4().hex},
        json={"decision": "Approved", "comment": "Closure confirmed"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "Completed"
    assert employee.post(path + "/readers", json={"user_id": ids[3]}).status_code == 200
    assert outsider.get(path).status_code == 200
    assert employee.delete(path + f"/readers/{ids[3]}").status_code == 200
    assert outsider.get(path).status_code == 404


def test_alignment_cards_metadata_and_hidden_cross_department_edges(environment):
    from app.models import Objective, Relation

    ids, cycle = environment
    factory = app.dependency_overrides[get_db]
    gen = factory()
    db = next(gen)
    parent = db.get(OrgUnit, db.get(User, ids[0]).org_id).parent_id
    unit = OrgUnit(name="Other department " + uuid.uuid4().hex[:8], parent_id=parent, unit_type="department")
    db.add(unit)
    db.flush()
    db.get(User, ids[3]).org_id = unit.id
    try:
        next(gen)
    except StopIteration:
        pass
    employee, outsider, division = TestClient(app), TestClient(app), TestClient(app)
    for client, uid in [(employee, ids[0]), (outsider, ids[3]), (division, ids[2])]:
        login(client, uid)
    payload = {
        "title": "Visible objective",
        "description": "Alignment test",
        "cycle_id": cycle,
        "theme": "Test",
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=10)),
    }
    own = employee.post("/api/v1/objectives", json=payload).json()
    other = outsider.post("/api/v1/objectives", json={**payload, "title": "Hidden department objective"}).json()
    gen = factory()
    db = next(gen)
    db.get(Objective, own["id"]).parent_id = other["id"]
    db.add(Relation(source_id=own["id"], target_id=other["id"], kind="contributes_to"))
    db.add(Relation(source_id=other["id"], target_id=own["id"], kind="depends_on"))
    try:
        next(gen)
    except StopIteration:
        pass
    visible = employee.get(f"/api/v1/alignment?cycle_id={cycle}").json()
    assert [n["id"] for n in visible["nodes"]] == [own["id"]]
    assert visible["edges"] == []
    assert visible["nodes"][0]["owner_name"] == "Employee"
    assert visible["nodes"][0]["org_name"]
    assert visible["nodes"][0]["progress"] is None
    assert visible["nodes"][0]["key_results"] == []
    full = division.get(f"/api/v1/alignment?cycle_id={cycle}").json()
    assert len({n["org_id"] for n in full["nodes"]}) == 2
    assert {e["kind"] for e in full["edges"]} == {"parent", "contributes_to", "depends_on"}


def test_session_requires_csrf(environment):
    ids, _ = environment
    client = TestClient(app)
    login(client, ids[0])
    del client.headers["X-CSRF-Token"]
    assert client.post("/auth/logout").status_code == 403
