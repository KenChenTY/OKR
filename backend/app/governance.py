import json
import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .business_time import business_date
from .config import settings
from .db import get_db
from .domain import due_after
from .models import Approval, ChangeRequest, Export, Job, KeyResult, Milestone, Objective, ObjectiveGrant, Revision, ScoreSnapshot, User, now
from .schemas import DecisionInput, Input, ObjectiveInput
from .security import current_user, require_owner, scope_ids
from .services import approver, audit, check_version, get_objective, lock, objective_query, objective_view

router = APIRouter(prefix="/api/v1", tags=["governance"])


class KRChange(Input):
    id: int
    baseline: Decimal = Field(max_digits=19, decimal_places=4)
    target: Decimal = Field(max_digits=19, decimal_places=4)
    weight: Decimal = Field(gt=0, le=100, max_digits=9, decimal_places=4)
    evidence_source: str | None = Field(default=None, min_length=1, max_length=255)


class ChangeInput(Input):
    objective: ObjectiveInput
    key_results: list[KRChange] = Field(default_factory=list, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


def validate_change(db, obj, body):
    if body.objective.cycle_id != obj.cycle_id:
        raise HTTPException(422, "批准后的目标不能更换周期")
    from .api import valid_cycle

    valid_cycle(db, body.objective)
    krs = list(db.scalars(select(KeyResult).where(KeyResult.objective_id == obj.id)))
    changes = {k.id: k for k in body.key_results}
    if len(changes) != len(body.key_results) or not set(changes).issubset({k.id for k in krs}):
        raise HTTPException(422, "KR变更有重复或未知ID")
    total = Decimal(0)
    for k in krs:
        proposal = changes.get(k.id)
        total += proposal.weight if proposal else k.weight
        if proposal:
            if k.value_type == "milestone" and (proposal.baseline != 0 or proposal.target != 100):
                raise HTTPException(422, "里程碑基线和目标必须为0及100")
            if proposal.target == proposal.baseline or (k.direction == "increase") != (proposal.target > proposal.baseline):
                raise HTTPException(422, "目标方向或基线无效")
            if k.value_type == "count" and any(v != v.to_integral_value() for v in (proposal.baseline, proposal.target)):
                raise HTTPException(422, "计数值必须是整数")
        for milestone in db.scalars(select(Milestone).where(Milestone.kr_id == k.id)):
            if not body.objective.start_date <= milestone.due_date <= body.objective.end_date:
                raise HTTPException(422, "变更日期必须包含全部里程碑")
    if total != 100:
        raise HTTPException(422, "变更后KR权重必须合计100")


@router.post("/objectives/{objective_id}/change-requests", status_code=201)
def request_change(
    objective_id: int,
    body: ChangeInput,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    obj = get_objective(db, user, objective_id, True)
    require_owner(user, obj)
    check_version(obj, request)
    if obj.status not in ("Approved", "Active"):
        raise HTTPException(409, "仅已批准或执行中目标可发起变更")
    if db.scalar(select(Approval.id).where(Approval.objective_id == obj.id, Approval.status == "Pending")):
        raise HTTPException(409, "结项审批期间不可申请定义变更")
    if db.scalar(select(ChangeRequest.id).where(ChangeRequest.objective_id == obj.id, ChangeRequest.status == "Pending")):
        raise HTTPException(409, "已有待审批变更")
    validate_change(db, obj, body)
    manager = approver(db, obj, "Manager", {user.id})
    division = approver(db, obj, "Division Head", {user.id, manager.id})
    if obj.visibility == "restricted" or body.objective.visibility == "restricted":
        for reader in (manager, division):
            if not db.get(ObjectiveGrant, (obj.id, reader.id)):
                db.add(ObjectiveGrant(objective_id=obj.id, user_id=reader.id, granted_by=user.id))
    change = ChangeRequest(
        objective_id=obj.id, proposed=body.model_dump_json(), reason=body.reason, submitted_by=user.id, assignee_id=manager.id, next_assignee_id=division.id
    )
    db.add(change)
    db.flush()
    audit(db, user, request, "RequestChange", obj.id, {"change_id": change.id, "before": objective_view(db, obj, True), "proposed": body.model_dump()})
    return {"id": change.id, "status": "Pending"}


@router.get("/change-requests")
def changes(objective_id: int | None = None, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    visible = objective_query(db, user).with_only_columns(Objective.id)
    query = select(ChangeRequest).where(ChangeRequest.objective_id.in_(visible))
    if objective_id:
        query = query.where(ChangeRequest.objective_id == objective_id)
    else:
        query = query.where(ChangeRequest.assignee_id == user.id, ChangeRequest.status == "Pending")
    return [
        {
            "id": c.id,
            "objective_id": c.objective_id,
            "status": c.status,
            "stage": c.stage,
            "reason": c.reason,
            "proposed": json.loads(c.proposed),
            "decisions": json.loads(c.decisions),
        }
        for c in db.scalars(query.order_by(ChangeRequest.id.desc()).limit(100))
    ]


@router.post("/change-requests/{change_id}/decisions")
def decide_change(
    change_id: int, body: DecisionInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    c = db.get(ChangeRequest, change_id)
    if not c:
        raise HTTPException(404)
    obj = get_objective(db, user, c.objective_id, True)
    db.refresh(c)
    if c.status != "Pending" or c.assignee_id != user.id or c.submitted_by == user.id or user.role != c.stage:
        raise HTTPException(409, "审批已处理或当前身份不可审批")
    if obj.org_id not in scope_ids(db, user):
        raise HTTPException(403)
    decisions = json.loads(c.decisions)
    decisions.append({"actor_id": user.id, "decision": body.decision, "comment": body.comment, "at": now().isoformat(), "stage": c.stage})
    c.decisions = json.dumps(decisions, ensure_ascii=False)
    if body.decision == "Rejected":
        c.status = "Rejected"
    elif c.stage == "Manager":
        next_user = db.get(User, c.next_assignee_id)
        if not next_user or not next_user.active or next_user.role != "Division Head":
            raise HTTPException(409, "下一审批人失效")
        c.stage, c.assignee_id = "Division Head", c.next_assignee_id
    else:
        proposal = ChangeInput.model_validate_json(c.proposed)
        validate_change(db, obj, proposal)
        for key, value in proposal.objective.model_dump().items():
            setattr(obj, key, value)
        for k in proposal.key_results:
            current = db.get(KeyResult, k.id)
            current.baseline, current.target, current.weight = k.baseline, k.target, k.weight
            if k.evidence_source is not None:
                current.evidence_source = k.evidence_source
        for kr in db.scalars(select(KeyResult).where(KeyResult.objective_id == obj.id)):
            kr.next_due = due_after(obj.start_date, kr.frequency, business_date(kr.last_checkin_at) if kr.last_checkin_at else obj.start_date)
        obj.revision += 1
        c.status = "Approved"
        db.flush()
        db.refresh(obj)
        db.add(Revision(objective_id=obj.id, revision=obj.revision, snapshot=json.dumps(jsonable_encoder(objective_view(db, obj, True)), ensure_ascii=False)))
    audit(db, user, request, "DecideChange", obj.id, {"change_id": c.id, "decision": body.decision, "comment": body.comment})
    return {"status": c.status, "stage": c.stage}


@router.post("/change-requests/{change_id}/withdraw")
def withdraw_change(change_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    change = db.get(ChangeRequest, change_id)
    if not change:
        raise HTTPException(404)
    obj = get_objective(db, user, change.objective_id, True)
    require_owner(user, obj)
    db.refresh(change)
    if change.status != "Pending":
        raise HTTPException(409)
    change.status = "Withdrawn"
    audit(db, user, request, "WithdrawChange", obj.id, {"change_id": change_id})
    return {"ok": True}


class GrantInput(Input):
    user_id: int


@router.post("/objectives/{objective_id}/readers")
def grant_reader(
    objective_id: int, body: GrantInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    obj = get_objective(db, user, objective_id, True)
    require_owner(user, obj)
    reader = db.get(User, body.user_id)
    if not reader or not reader.active or reader.role == "System Admin":
        raise HTTPException(422, "读者身份无效")
    if not db.get(ObjectiveGrant, (obj.id, reader.id)):
        db.add(ObjectiveGrant(objective_id=obj.id, user_id=reader.id, granted_by=user.id))
    audit(db, user, request, "GrantRead", obj.id, {"user_id": reader.id})
    return {"ok": True}


@router.delete("/objectives/{objective_id}/readers/{reader_id}")
def revoke_reader(
    objective_id: int, reader_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    obj = get_objective(db, user, objective_id, True)
    require_owner(user, obj)
    pending = db.scalar(
        select(Approval.id).where(
            Approval.objective_id == obj.id, Approval.status == "Pending", (Approval.assignee_id == reader_id) | (Approval.next_assignee_id == reader_id)
        )
    )
    pending_change = db.scalar(
        select(ChangeRequest.id).where(
            ChangeRequest.objective_id == obj.id,
            ChangeRequest.status == "Pending",
            (ChangeRequest.assignee_id == reader_id) | (ChangeRequest.next_assignee_id == reader_id),
        )
    )
    if pending or pending_change:
        raise HTTPException(409, "不能在审批期间撤销审批人的读取权限")
    grant = db.get(ObjectiveGrant, (obj.id, reader_id))
    if grant:
        db.delete(grant)
    audit(db, user, request, "RevokeRead", obj.id, {"user_id": reader_id})
    return {"ok": True}


class ExportInput(Input):
    cycle_id: int | None = None


@router.post("/exports", status_code=202)
def create_export(body: ExportInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    if user.role not in ("Manager", "Division Head", "PMO", "Audit"):
        raise HTTPException(403, "当前角色没有批量导出权限")
    lock(db, f"export-user:{user.id}")
    if db.scalar(select(func.count()).select_from(Export).where(Export.user_id == user.id, Export.status == "Pending")) >= 3:
        raise HTTPException(429, "最多同时运行3个导出任务")
    record = Export(user_id=user.id, cycle_id=body.cycle_id, storage_key=uuid.uuid4().hex + ".csv", expires_at=now() + timedelta(hours=24))
    db.add(record)
    db.flush()
    db.add(Job(kind="export", payload=json.dumps({"export_id": record.id}), dedupe_key=f"export:{record.id}"))
    audit(db, user, request, "RequestExport", None, {"export_id": record.id, "cycle_id": body.cycle_id})
    return {"id": record.id, "status": record.status}


@router.get("/exports")
def exports(user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    return [
        {"id": e.id, "status": e.status, "expires_at": e.expires_at, "created_at": e.created_at}
        for e in db.scalars(select(Export).where(Export.user_id == user.id).order_by(Export.id.desc()).limit(20))
    ]


@router.get("/exports/{export_id}/download")
def download_export(export_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    record = db.get(Export, export_id)
    if not record or record.user_id != user.id:
        raise HTTPException(404)
    if user.role not in ("Manager", "Division Head", "PMO", "Audit"):
        raise HTTPException(403)
    if record.status != "Completed" or record.expires_at < now():
        raise HTTPException(409, "导出未完成或已过期")
    for oid in json.loads(record.object_ids):
        get_objective(db, user, oid)
    path = settings().storage_root.resolve() / "exports" / record.storage_key
    if not path.is_file():
        raise HTTPException(503, "导出文件不可用")
    audit(db, user, request, "DownloadExport", None, {"export_id": record.id})
    return FileResponse(path, filename=f"okr-{record.id}.csv", media_type="text/csv", headers={"Cache-Control": "no-store"})


@router.get("/objectives/{objective_id}/snapshots")
def snapshots(objective_id: int, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    get_objective(db, user, objective_id)
    return [
        {"date": s.snapshot_date, "formula_version": s.formula_version, "value": json.loads(s.payload)}
        for s in db.scalars(select(ScoreSnapshot).where(ScoreSnapshot.objective_id == objective_id).order_by(ScoreSnapshot.snapshot_date.desc()).limit(100))
    ]
