from sqlalchemy import true
import base64
import hashlib
import json
from dataclasses import asdict
from decimal import Decimal

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_, select, text

from .business_time import today as business_today
from .config import settings
from .domain import HealthPolicy, health, planned_progress, progress, weighted_score
from .models import Audit, Evidence, Idempotency, KeyResult, Milestone, Objective, ObjectiveGrant, OrgUnit, Revision, User
from .security import can_read, scope_ids


def etag(obj):
    return '"' + base64.b64encode(obj.row_version).decode() + '"'


def check_version(obj, request):
    value = request.headers.get("if-match")
    if not value:
        raise HTTPException(428, "请提供If-Match版本")
    if value != etag(obj):
        raise HTTPException(412, "数据已被修改，请刷新后重试")


def lock(db, resource):
    # Transaction-owned SQL Server application lock serializes cross-row invariants.
    result = db.execute(
        text(
            "SET NOCOUNT ON; DECLARE @r int; EXEC @r = sys.sp_getapplock @Resource=:resource, @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=5000; SELECT @r"
        ),
        {"resource": "okr:" + str(resource)},
    ).scalar()
    if result is None or result < 0:
        raise HTTPException(409, "其他操作正在进行，请稍后重试")


def objective_query(db, user):
    query = select(Objective)
    if user.role == "System Admin":
        return query.where(Objective.id == -1)
    if user.role == "Employee":
        return query.where(or_(Objective.owner_id == user.id, Objective.id.in_(select(ObjectiveGrant.objective_id).where(ObjectiveGrant.user_id == user.id))))
    return query.where(
        or_(
            Objective.owner_id == user.id,
            (Objective.visibility == "organization") & Objective.org_id.in_(scope_ids(db, user)),
            Objective.id.in_(select(ObjectiveGrant.objective_id).where(ObjectiveGrant.user_id == user.id)),
        )
    )


def get_objective(db, user, objective_id, write=False):
    if write:
        lock(db, f"objective:{objective_id}")
    obj = db.scalar(select(Objective).where(Objective.id == objective_id).execution_options(populate_existing=True))
    if not obj or not can_read(db, user, obj):
        raise HTTPException(404, "目标不存在或无访问权限")
    return obj


def audit(db, user, request, action, objective_id, detail):
    db.add(
        Audit(
            actor_id=user.id,
            action=action,
            objective_id=objective_id,
            detail=json.dumps(detail, ensure_ascii=False, default=str),
            request_id=request.state.request_id,
        )
    )


def idempotent(db, user, request, body):
    key = request.headers.get("idempotency-key", "")
    if not key or len(key) > 100:
        raise HTTPException(422, "请提供不超过100字符的Idempotency-Key")
    full = hashlib.sha256(f"{user.id}:{request.url.path}:{key}".encode()).hexdigest()
    payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    lock(db, f"idempotency:{full}")
    record = db.get(Idempotency, full)
    if record and record.digest != payload_hash:
        raise HTTPException(409, "幂等键已用于不同请求")
    return full, payload_hash, json.loads(record.response) if record else None


def save_result(db, key, payload_hash, result):
    normalized = jsonable_encoder(result)
    db.add(Idempotency(key=key, digest=payload_hash, response=json.dumps(normalized)))
    return normalized


def kr_view(db, kr, obj):
    today = business_today()
    raw, value = progress(kr.baseline, kr.current_value, kr.target)
    planned = planned_progress(obj.start_date, obj.end_date, today)
    milestones = list(db.scalars(select(Milestone).where(Milestone.kr_id == kr.id)))
    if kr.value_type == "milestone":
        total = sum((m.weight for m in milestones), Decimal(0))
        planned = sum((m.weight for m in milestones if m.due_date <= today), Decimal(0)) / total * 100 if total else Decimal(0)
    cfg = settings()
    policy = HealthPolicy(cfg.health_grace_days, cfg.health_red_confidence, cfg.health_amber_confidence, cfg.health_red_lag, cfg.health_amber_lag)
    state = health(value, planned, kr.confidence, kr.last_checkin_at, kr.next_due, today, kr.severe_blocker, policy)
    return {
        "id": kr.id,
        "name": kr.name,
        "value_type": kr.value_type,
        "direction": kr.direction,
        "baseline": str(kr.baseline),
        "current_value": str(kr.current_value),
        "target": str(kr.target),
        "weight": str(kr.weight),
        "unit": kr.unit,
        "currency": kr.currency,
        "frequency": kr.frequency,
        "evidence_source": kr.evidence_source,
        "progress": str(value.quantize(Decimal("0.01"))),
        "raw_progress": str(raw.quantize(Decimal("0.01"))),
        "health": state,
        "confidence": kr.confidence,
        "next_due": str(kr.next_due),
        "last_checkin_at": kr.last_checkin_at,
        "severe_blocker": kr.severe_blocker,
        "etag": etag(kr),
        "health_policy": asdict(policy),
        "milestones": [{"id": m.id, "name": m.name, "weight": str(m.weight), "due_date": m.due_date, "accepted_at": m.accepted_at} for m in milestones],
    }


def objective_view(db, obj, detail=False):
    records = list(db.scalars(select(KeyResult).where(KeyResult.objective_id == obj.id).order_by(KeyResult.id)))
    krs = [kr_view(db, k, obj) for k in records]
    score = weighted_score([(progress(k.baseline, k.current_value, k.target)[1], k.weight) for k in records])
    owner, org = db.get(User, obj.owner_id), db.get(OrgUnit, obj.org_id)
    result = {
        "id": obj.id,
        "code": obj.code,
        "title": obj.title,
        "description": obj.description,
        "owner_id": obj.owner_id,
        "owner_name": owner.name,
        "org_id": obj.org_id,
        "org_name": org.name,
        "cycle_id": obj.cycle_id,
        "theme": obj.theme,
        "priority": obj.priority,
        "level": obj.level,
        "visibility": obj.visibility,
        "start_date": str(obj.start_date),
        "end_date": str(obj.end_date),
        "status": obj.status,
        "parent_id": obj.parent_id,
        "revision": obj.revision,
        "etag": etag(obj),
        "kr_count": len(krs),
        "progress": str(score.quantize(Decimal("0.01"))) if score is not None else None,
        "raw_score": str(score) if score is not None else None,
        "health_counts": {s: sum(k["health"] == s for k in krs) for s in ("Green", "Amber", "Red", "Gray")},
    }
    if detail:
        result["key_results"] = krs
    if obj.status in ("Completed", "Archived"):
        revision = db.scalar(select(Revision).where(Revision.objective_id == obj.id).order_by(Revision.revision.desc()).limit(1))
        frozen = json.loads(revision.snapshot) if revision else {}
        if frozen.get("status") == "Completed":
            result["progress"] = frozen["progress"]
            result["raw_score"] = frozen.get("raw_score", frozen["progress"])
            result["health_counts"] = frozen["health_counts"]
            if detail:
                result["key_results"] = frozen.get("key_results", krs)
    return result


def approver(db, obj, role, excluded):
    # Closest ancestor matching role, frozen into each task at submission.
    unit = db.get(OrgUnit, obj.org_id)
    while unit:
        user = db.scalar(select(User).where(User.org_id == unit.id, User.role == role, User.active == true(), User.id.not_in(excluded)).order_by(User.id))
        if user:
            return user
        unit = db.get(OrgUnit, unit.parent_id) if unit.parent_id else None
    raise HTTPException(409, f"未配置可用的{role}审批人")


def validate_evidence(db, objective_id, ids):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "证据引用不能重复")
    for evidence_id in ids:
        e = db.get(Evidence, evidence_id)
        if not e or e.objective_id != objective_id or e.status != "Available":
            raise HTTPException(422, "证据不存在、未通过扫描或不属于当前目标")
