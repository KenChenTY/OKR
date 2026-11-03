from sqlalchemy import true
import json
import uuid
from datetime import timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .business_time import today, business_date
from .domain import due_after, would_cycle
from .models import (
    Approval,
    Audit,
    ChangeRequest,
    CheckIn,
    CheckInEvidence,
    Cycle,
    Evidence,
    Job,
    KeyResult,
    Meeting,
    Milestone,
    Notification,
    Objective,
    ObjectiveGrant,
    OrgUnit,
    Relation,
    ReviewAction,
    Revision,
    User,
    now,
)
from .schemas import CheckInInput, DecisionInput, KRInput, MeetingInput, ObjectiveInput, RelationInput, TransitionInput, Input
from pydantic import Field
from .security import current_user, require_owner, scope_ids
from .services import (
    approver,
    audit,
    check_version,
    etag,
    get_objective,
    idempotent,
    kr_view,
    lock,
    objective_query,
    objective_view,
    save_result,
    validate_evidence,
)

router = APIRouter(prefix="/api/v1", tags=["OKR"])


class EvidenceSourceInput(Input):
    evidence_source: str = Field(min_length=1, max_length=255)


@router.patch("/key-results/{kr_id}/evidence-source")
def edit_evidence_source(kr_id: int, body: EvidenceSourceInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    kr = db.get(KeyResult, kr_id)
    if not kr:
        raise HTTPException(404)
    obj = get_objective(db, user, kr.objective_id, True)
    require_owner(user, obj)
    db.refresh(kr)
    check_version(kr, request)
    if obj.status != "Draft":
        raise HTTPException(409, "已批准的KR证据来源需通过变更审批修改")
    before = kr.evidence_source
    kr.evidence_source = body.evidence_source
    obj.revision += 1
    audit(db, user, request, "EditEvidenceSource", obj.id, {"kr_id": kr.id, "before": before, "after": body.evidence_source})
    db.flush()
    db.refresh(kr)
    return kr_view(db, kr, obj)


@router.get("/me")
def me(request: Request, user: User = Depends(current_user, scope="function")):
    return {"id": user.id, "name": user.name, "role": user.role, "org_id": user.org_id, "csrf": request.state.session.csrf}


@router.get("/catalog")
def catalog(user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    scopes = scope_ids(db, user)
    return {
        "cycles": [
            {"id": c.id, "name": c.name, "start_date": c.start_date, "end_date": c.end_date}
            for c in db.scalars(select(Cycle).order_by(Cycle.start_date.desc()))
        ],
        "org_units": [{"id": o.id, "name": o.name, "parent_id": o.parent_id} for o in db.scalars(select(OrgUnit).where(OrgUnit.id.in_(scopes)))],
        "users": [{"id": u.id, "name": u.name, "role": u.role} for u in db.scalars(select(User).where(User.org_id.in_(scopes), User.active == true()))],
    }


@router.get("/objectives")
def objectives(
    cycle_id: int | None = None,
    level: str | None = None,
    org_id: int | None = None,
    status: str | None = None,
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    query = objective_query(db, user)
    if cycle_id:
        query = query.where(Objective.cycle_id == cycle_id)
    if status:
        query = query.where(Objective.status == status)
    if level:
        query = query.where(Objective.level == level)
    if org_id:
        query = query.where(Objective.org_id == org_id)
    if q:
        query = query.where(Objective.title.contains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {
        "items": [objective_view(db, obj) for obj in db.scalars(query.order_by(Objective.id.desc()).offset((page - 1) * page_size).limit(page_size))],
        "total": total,
        "page": page,
    }


def valid_cycle(db, body):
    cycle = db.get(Cycle, body.cycle_id)
    if not cycle or body.start_date < cycle.start_date or body.end_date > cycle.end_date:
        raise HTTPException(422, "目标日期必须在所选周期内")


@router.post("/objectives", status_code=201)
def create_objective(
    body: ObjectiveInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    if user.role not in ("Employee", "Manager", "Division Head", "PMO"):
        raise HTTPException(403, "没有创建目标权限")
    valid_cycle(db, body)
    obj = Objective(**body.model_dump(), code="OKR-" + uuid.uuid4().hex[:12].upper(), owner_id=user.id, org_id=user.org_id)
    db.add(obj)
    db.flush()
    db.refresh(obj)
    audit(db, user, request, "Create", obj.id, body.model_dump())
    return objective_view(db, obj, True)


@router.get("/objectives/{objective_id}")
def objective_detail(
    objective_id: int, response: Response, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    obj = get_objective(db, user, objective_id)
    response.headers["ETag"] = etag(obj)
    result = objective_view(db, obj, True)
    result["approvals"] = [
        {
            "id": a.id,
            "stage": a.stage,
            "status": a.status,
            "assignee_id": a.assignee_id,
            "assignee_name": db.get(User, a.assignee_id).name,
            "comment": a.comment,
            "revision": a.revision,
            "decided_at": a.decided_at,
        }
        for a in db.scalars(select(Approval).where(Approval.objective_id == obj.id).order_by(Approval.id))
    ]
    result["evidence"] = [
        {
            "id": e.id,
            "name": e.name,
            "kind": e.kind,
            "status": e.status,
            "previous_id": e.previous_id,
            "uploaded_at": e.uploaded_at,
            "uploaded_by": e.uploaded_by,
            "uploader": db.get(User, e.uploaded_by).name,
            "size": e.size,
            "url": e.url,
        }
        for e in db.scalars(select(Evidence).where(Evidence.objective_id == obj.id).order_by(Evidence.id.desc()))
    ]
    return result


@router.patch("/objectives/{objective_id}")
def edit_objective(
    objective_id: int,
    body: ObjectiveInput,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    obj = get_objective(db, user, objective_id, True)
    require_owner(user, obj)
    check_version(obj, request)
    if obj.status != "Draft":
        raise HTTPException(409, "仅草稿可直接修改")
    valid_cycle(db, body)
    before = objective_view(db, obj)
    if body.cycle_id != obj.cycle_id and (
        obj.parent_id
        or db.scalar(select(Objective.id).where(Objective.parent_id == obj.id))
        or db.scalar(select(Relation.id).where((Relation.source_id == obj.id) | (Relation.target_id == obj.id)))
    ):
        raise HTTPException(409, "已建立对齐关系的目标不能直接更换周期")
    for kr in db.scalars(select(KeyResult).where(KeyResult.objective_id == obj.id)):
        for milestone in db.scalars(select(Milestone).where(Milestone.kr_id == kr.id)):
            if not body.start_date <= milestone.due_date <= body.end_date:
                raise HTTPException(422, "修改后日期不能排除已有里程碑")
        kr.next_due = due_after(body.start_date, kr.frequency, body.start_date)
    for key, value in body.model_dump().items():
        setattr(obj, key, value)
    db.flush()
    db.refresh(obj)
    audit(db, user, request, "Update", obj.id, {"before": before, "after": body.model_dump()})
    return objective_view(db, obj, True)


@router.post("/objectives/{objective_id}/key-results", status_code=201)
def add_kr(
    objective_id: int, body: KRInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    obj = get_objective(db, user, objective_id, True)
    require_owner(user, obj)
    check_version(obj, request)
    if obj.status != "Draft":
        raise HTTPException(409, "仅草稿可新增KR")
    data = body.model_dump(exclude={"milestones"})
    kr = KeyResult(**data, objective_id=obj.id, current_value=body.baseline, next_due=due_after(obj.start_date, body.frequency, obj.start_date))
    db.add(kr)
    db.flush()
    for milestone in body.milestones:
        if not obj.start_date <= milestone.due_date <= obj.end_date:
            raise HTTPException(422, "里程碑日期必须在目标周期内")
        db.add(Milestone(**milestone.model_dump(), kr_id=kr.id))
    # Change the objective rowversion when its KR definition changes.
    obj.revision += 1
    db.flush()
    db.refresh(kr)
    audit(db, user, request, "CreateKR", obj.id, body.model_dump())
    return kr_view(db, kr, obj)


@router.delete("/key-results/{kr_id}")
def delete_kr(kr_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    kr = db.get(KeyResult, kr_id)
    if not kr:
        raise HTTPException(404)
    obj = get_objective(db, user, kr.objective_id, True)
    require_owner(user, obj)
    db.refresh(kr)
    check_version(kr, request)
    if obj.status != "Draft" or db.scalar(select(func.count()).select_from(CheckIn).where(CheckIn.kr_id == kr_id)):
        raise HTTPException(409, "仅未产生更新记录的草稿KR可删除")
    for m in db.scalars(select(Milestone).where(Milestone.kr_id == kr.id)):
        db.delete(m)
    db.delete(kr)
    obj.revision += 1
    audit(db, user, request, "DeleteKR", obj.id, {"id": kr.id, "name": kr.name})
    return {"ok": True}


@router.post("/objectives/{objective_id}/submit")
def submit(objective_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    obj = get_objective(db, user, objective_id, True)
    require_owner(user, obj)
    key, hash_, old = idempotent(db, user, request, {})
    if old:
        return old
    check_version(obj, request)
    if obj.status != "Draft":
        raise HTTPException(409, "当前目标不处于草稿状态")
    krs = list(db.scalars(select(KeyResult).where(KeyResult.objective_id == obj.id)))
    if not krs or sum(k.weight for k in krs) != 100:
        raise HTTPException(422, "请至少添加一个KR，且权重之和必须为100")
    manager = approver(db, obj, "Manager", {user.id})
    division = approver(db, obj, "Division Head", {user.id, manager.id})
    if obj.visibility == "restricted":
        for reader in (manager, division):
            if not db.get(ObjectiveGrant, (obj.id, reader.id)):
                db.add(ObjectiveGrant(objective_id=obj.id, user_id=reader.id, granted_by=user.id))
    obj.revision += 1
    obj.status = "Submitted"
    evidence_ids = list(db.scalars(select(Evidence.id).where(Evidence.objective_id == obj.id, Evidence.status == "Available")))
    snapshot = objective_view(db, obj, True) | {"evidence_version_ids": evidence_ids}
    db.add(Revision(objective_id=obj.id, revision=obj.revision, snapshot=json.dumps(snapshot, default=str, ensure_ascii=False)))
    db.add(Approval(objective_id=obj.id, revision=obj.revision, stage="Manager", assignee_id=manager.id, next_assignee_id=division.id, submitted_by=user.id))
    db.add(
        Job(
            kind="notify",
            payload=json.dumps({"user_id": manager.id, "objective_id": obj.id, "message": "有新的目标审批待办"}),
            dedupe_key=f"submit:{obj.id}:{obj.revision}",
        )
    )
    audit(db, user, request, "Submit", obj.id, {"revision": obj.revision})
    db.flush()
    db.refresh(obj)
    return save_result(db, key, hash_, objective_view(db, obj, True))


@router.get("/approvals")
def approvals(user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    result = []
    for task in db.scalars(select(Approval).where(Approval.assignee_id == user.id, Approval.status == "Pending")):
        obj = db.scalar(objective_query(db, user).where(Objective.id == task.objective_id))
        if obj:
            result.append({"id": task.id, "stage": task.stage, "revision": task.revision, "objective": objective_view(db, obj)})
    return result


@router.post("/workflow-tasks/{task_id}/decisions")
def decide(
    task_id: int, body: DecisionInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    task = db.get(Approval, task_id)
    if not task:
        raise HTTPException(404)
    obj = get_objective(db, user, task.objective_id, True)
    db.refresh(task)
    if task.assignee_id != user.id or task.submitted_by == user.id:
        raise HTTPException(403, "不允许处理此审批或自审批")
    key, hash_, old = idempotent(db, user, request, body.model_dump())
    if old:
        return old
    check_version(obj, request)
    expected_role = "Manager" if task.stage in ("Manager", "Completion") else "Division Head"
    required_status = "Active" if task.stage == "Completion" else "Submitted"
    if user.role != expected_role or task.status != "Pending" or obj.status != required_status or obj.org_id not in scope_ids(db, user):
        raise HTTPException(409, "审批已处理或审批资格已变更")
    task.status, task.comment, task.decided_at = body.decision, body.comment, now()
    db.flush()  # Release the filtered pending uniqueness slot before next stage.
    if task.stage == "Completion":
        if body.decision == "Approved":
            obj.status = "Completed"
            obj.revision += 1
            db.add(Revision(objective_id=obj.id, revision=obj.revision, snapshot=json.dumps(objective_view(db, obj, True), default=str, ensure_ascii=False)))
    elif body.decision == "Rejected":
        obj.status = "Draft"
    elif task.stage == "Manager":
        next_user = db.get(User, task.next_assignee_id)
        if not next_user or not next_user.active or next_user.role != "Division Head":
            raise HTTPException(409, "下一审批人已失效，请撤回后重新提交")
        db.add(Approval(objective_id=obj.id, revision=task.revision, stage="Division Head", assignee_id=next_user.id, submitted_by=task.submitted_by))
        db.add(
            Job(
                kind="notify",
                payload=json.dumps({"user_id": next_user.id, "objective_id": obj.id, "message": "有新的事业部目标审批待办"}),
                dedupe_key=f"approval-next:{task.id}",
            )
        )
    else:
        obj.status = "Approved"
    # Manager approval must also invalidate the objective's concurrency token.
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(obj, "status")
    audit(db, user, request, "Approve" if body.decision == "Approved" else "Reject", obj.id, {"task_id": task.id, "comment": body.comment})
    db.flush()
    db.refresh(obj)
    return save_result(db, key, hash_, objective_view(db, obj, True))


@router.post("/objectives/{objective_id}/transitions")
def transition(
    objective_id: int,
    body: TransitionInput,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    obj = get_objective(db, user, objective_id, True)
    check_version(obj, request)
    before = obj.status
    if db.scalar(select(ChangeRequest.id).where(ChangeRequest.objective_id == obj.id, ChangeRequest.status == "Pending")):
        raise HTTPException(409, "请先完成或撤回正在审批的变更申请")
    if body.action == "withdraw" and obj.status == "Submitted":
        require_owner(user, obj)
        obj.status = "Draft"
    elif body.action == "activate" and obj.status == "Approved":
        require_owner(user, obj)
        if today() < obj.start_date:
            raise HTTPException(409, "尚未到达开始日期")
        obj.status = "Active"
    elif body.action == "request_completion" and obj.status == "Active":
        require_owner(user, obj)
        if db.scalar(select(Approval.id).where(Approval.objective_id == obj.id, Approval.status == "Pending")):
            raise HTTPException(409, "已有待处理的结项申请")
        manager = approver(db, obj, "Manager", {user.id})
        if obj.visibility == "restricted" and not db.get(ObjectiveGrant, (obj.id, manager.id)):
            db.add(ObjectiveGrant(objective_id=obj.id, user_id=manager.id, granted_by=user.id))
        db.add(Approval(objective_id=obj.id, revision=obj.revision, stage="Completion", assignee_id=manager.id, submitted_by=user.id, comment=body.reason))
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(obj, "status")
    elif body.action == "complete" and obj.status == "Active":
        if user.role not in ("Manager", "Division Head") or user.id == obj.owner_id or obj.org_id not in scope_ids(db, user):
            raise HTTPException(403, "结项需由独立经理确认")
        task = db.scalar(
            select(Approval).where(
                Approval.objective_id == obj.id, Approval.status == "Pending", Approval.stage == "Completion", Approval.assignee_id == user.id
            )
        )
        if not task:
            raise HTTPException(409, "需由负责人先提交结项申请，再由指定经理确认")
        task.status, task.comment, task.decided_at = "Approved", body.reason, now()
        obj.status = "Completed"
        db.add(Revision(objective_id=obj.id, revision=obj.revision + 1, snapshot=json.dumps(objective_view(db, obj, True), default=str, ensure_ascii=False)))
        obj.revision += 1
    elif body.action == "cancel" and obj.status in ("Draft", "Submitted", "Approved", "Active"):
        if obj.status == "Draft":
            require_owner(user, obj)
        elif user.role not in ("Manager", "Division Head") or user.id == obj.owner_id or obj.org_id not in scope_ids(db, user):
            raise HTTPException(403, "非草稿取消需由独立经理确认")
        obj.status = "Cancelled"
    elif body.action == "archive" and obj.status in ("Completed", "Cancelled"):
        if user.role not in ("Manager", "Division Head", "PMO") or obj.org_id not in scope_ids(db, user):
            raise HTTPException(403)
        obj.status = "Archived"
    else:
        raise HTTPException(409, "不允许当前状态迁移")
    if obj.status in ("Draft", "Cancelled"):
        for task in db.scalars(select(Approval).where(Approval.objective_id == obj.id, Approval.status == "Pending")):
            task.status, task.comment, task.decided_at = "Withdrawn", body.reason, now()
    audit(db, user, request, body.action, obj.id, {"before": before, "after": obj.status, "reason": body.reason})
    db.flush()
    db.refresh(obj)
    return objective_view(db, obj, True)


@router.post("/key-results/{kr_id}/check-ins", status_code=201)
def checkin(
    kr_id: int, body: CheckInInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    kr = db.get(KeyResult, kr_id)
    if not kr:
        raise HTTPException(404)
    obj = get_objective(db, user, kr.objective_id, True)
    require_owner(user, obj)
    db.refresh(kr)
    key, hash_, old = idempotent(db, user, request, body.model_dump())
    if old:
        return old
    check_version(kr, request)
    if obj.status != "Active":
        raise HTTPException(409, "仅执行中的目标可更新")
    if kr.value_type == "milestone":
        raise HTTPException(422, "里程碑进度由验收节点自动计算")
    if kr.value_type == "count" and body.current_value != body.current_value.to_integral_value():
        raise HTTPException(422, "计数必须为整数")
    if body.effective_at.tzinfo is None:
        raise HTTPException(422, "更新时间必须包含时区")
    effective = body.effective_at.astimezone(timezone.utc).replace(tzinfo=None)
    if effective > now() or (kr.last_checkin_at and effective <= kr.last_checkin_at) or business_date(effective) < obj.start_date:
        raise HTTPException(422, "更新时间不得在未来或早于上一条记录及目标开始日期")
    validate_evidence(db, obj.id, body.evidence_version_ids)
    before = str(kr.current_value)
    data = body.model_dump(exclude={"evidence_version_ids", "severe_blocker", "effective_at"})
    record = CheckIn(**data, effective_at=effective, actor_id=user.id, kr_id=kr.id)
    db.add(record)
    db.flush()
    for eid in body.evidence_version_ids:
        db.add(CheckInEvidence(checkin_id=record.id, evidence_id=eid))
    kr.current_value, kr.confidence, kr.severe_blocker = body.current_value, body.confidence, body.severe_blocker
    kr.last_checkin_at = effective
    kr.next_due = due_after(obj.start_date, kr.frequency, business_date(effective))
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(obj, "status")
    audit(db, user, request, "CheckIn", obj.id, {"kr_id": kr.id, "before": before, "after": str(kr.current_value), "checkin_id": record.id})
    db.flush()
    db.refresh(kr)
    return save_result(db, key, hash_, {"check_in_id": record.id, **kr_view(db, kr, obj)})


@router.get("/key-results/{kr_id}/check-ins")
def checkin_history(
    kr_id: int, page: int = Query(1, ge=1), user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    kr = db.get(KeyResult, kr_id)
    if not kr:
        raise HTTPException(404)
    get_objective(db, user, kr.objective_id)
    return [
        {
            "id": c.id,
            "current_value": str(c.current_value),
            "confidence": c.confidence,
            "commentary": c.commentary,
            "risks": c.risks,
            "blockers": c.blockers,
            "next_action": c.next_action,
            "effective_at": c.effective_at,
            "actor": db.get(User, c.actor_id).name,
            "evidence_version_ids": list(db.scalars(select(CheckInEvidence.evidence_id).where(CheckInEvidence.checkin_id == c.id))),
        }
        for c in db.scalars(select(CheckIn).where(CheckIn.kr_id == kr_id).order_by(CheckIn.id.desc()).offset((page - 1) * 50).limit(50))
    ]


@router.post("/milestones/{milestone_id}/accept")
def accept_milestone(
    milestone_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    m = db.get(Milestone, milestone_id)
    if not m:
        raise HTTPException(404)
    kr = db.get(KeyResult, m.kr_id)
    obj = get_objective(db, user, kr.objective_id, True)
    db.refresh(kr)
    db.refresh(m)
    check_version(kr, request)
    if obj.status != "Active" or m.accepted_at:
        raise HTTPException(409, "目标未执行或节点已验收")
    if user.role not in ("Manager", "Division Head") or user.id == obj.owner_id or obj.org_id not in scope_ids(db, user):
        raise HTTPException(403, "里程碑需独立经理验收")
    m.accepted_at, m.accepted_by = now(), user.id
    db.flush()
    milestones = list(db.scalars(select(Milestone).where(Milestone.kr_id == kr.id)))
    kr.current_value = sum(x.weight for x in milestones if x.accepted_at) / sum(x.weight for x in milestones) * 100
    kr.last_checkin_at, kr.next_due = now(), due_after(obj.start_date, kr.frequency, today())
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(obj, "status")
    db.add(
        CheckIn(kr_id=kr.id, actor_id=user.id, current_value=kr.current_value, confidence=kr.confidence, commentary=f"验收里程碑：{m.name}", effective_at=now())
    )
    audit(db, user, request, "AcceptMilestone", obj.id, {"milestone_id": m.id})
    db.flush()
    db.refresh(kr)
    return kr_view(db, kr, obj)


@router.get("/alignment")
def alignment(cycle_id: int | None = None, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    query = objective_query(db, user)
    if cycle_id:
        query = query.where(Objective.cycle_id == cycle_id)
    objects = list(db.scalars(query))
    ids = {o.id for o in objects}
    edges = [{"source": r.source_id, "target": r.target_id, "kind": r.kind} for r in db.scalars(select(Relation)) if r.source_id in ids and r.target_id in ids]
    edges += [{"source": o.id, "target": o.parent_id, "kind": "parent"} for o in objects if o.parent_id in ids]
    nodes = []
    for obj in objects:
        view = objective_view(db, obj, True)
        nodes.append({"id": obj.id, "title": obj.title, "level": obj.level, "status": obj.status,
                      "owner_id": obj.owner_id, "owner_name": view["owner_name"], "org_id": obj.org_id,
                      "org_name": view["org_name"], "progress": view["progress"], "kr_count": view["kr_count"],
                      "key_results": [{"id": k["id"], "name": k["name"], "progress": k["progress"], "health": k["health"]} for k in view["key_results"][:2]]})
    return {"nodes": nodes, "edges": edges}


@router.post("/objectives/{objective_id}/relations")
def add_relation(
    objective_id: int,
    body: RelationInput,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    lock(db, "alignment-graph")
    obj = get_objective(db, user, objective_id, True)
    target = get_objective(db, user, body.target_id)
    require_owner(user, obj)
    check_version(obj, request)
    if obj.status != "Draft" or obj.cycle_id != target.cycle_id:
        raise HTTPException(409, "仅可编辑同周期草稿的对齐关系")
    relations = db.scalars(select(Relation)).all()
    if body.kind == "depends_on":
        edges = [(r.source_id, r.target_id) for r in relations if r.kind == body.kind]
    else:
        edges = [(r.source_id, r.target_id) for r in relations if r.kind == "contributes_to"]
        edges += [
            (o.id, o.parent_id) for o in db.scalars(select(Objective).where(Objective.parent_id.is_not(None))) if not (body.kind == "parent" and o.id == obj.id)
        ]
    if would_cycle(edges, obj.id, target.id):
        raise HTTPException(422, "该关系将产生循环")
    if body.kind == "parent":
        obj.parent_id = target.id
    else:
        if any(r.source_id == obj.id and r.target_id == target.id and r.kind == body.kind for r in relations):
            raise HTTPException(409, "关系已存在")
        db.add(Relation(source_id=obj.id, target_id=target.id, kind=body.kind))
    obj.revision += 1
    audit(db, user, request, "Alignment", obj.id, body.model_dump())
    return {"ok": True}


@router.get("/dashboards/executive")
def dashboard(cycle_id: int | None = None, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    query = objective_query(db, user)
    if cycle_id:
        query = query.where(Objective.cycle_id == cycle_id)
    objects = [objective_view(db, o) for o in db.scalars(query)]
    effective = [o for o in objects if o["status"] not in ("Draft", "Cancelled", "Archived")]
    scores = [Decimal(o["raw_score"]) for o in effective if o["raw_score"] is not None]
    return {
        "as_of": now(),
        "formula_version": "1.0",
        "total": len(objects),
        "effective_count": len(effective),
        "achievement": str((sum(scores) / len(scores)).quantize(Decimal("0.01"))) if scores else None,
        "health": {s: sum(o["health_counts"][s] for o in effective) for s in ("Green", "Amber", "Red", "Gray")},
        "statuses": {s: sum(o["status"] == s for o in objects) for s in ("Draft", "Submitted", "Approved", "Active", "Completed", "Cancelled", "Archived")},
        "themes": [{"name": t, "count": sum(o["theme"] == t for o in objects)} for t in sorted({o["theme"] for o in objects})],
        "attention": [o for o in effective if o["health_counts"]["Red"] or o["health_counts"]["Amber"] or o["health_counts"]["Gray"]][:10],
    }


@router.get("/audit-events")
def audit_events(
    page: int = Query(1, ge=1),
    objective_id: int | None = None,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    if user.role not in ("Audit", "PMO", "Manager", "Division Head"):
        raise HTTPException(403, "无审计查询权限")
    visible = objective_query(db, user).with_only_columns(Objective.id)
    own_system_events = Audit.objective_id.is_(None)
    if user.role != "Audit":
        own_system_events = own_system_events & (Audit.actor_id == user.id)
    query = select(Audit).where(or_(Audit.objective_id.in_(visible), own_system_events))
    if objective_id:
        query = query.where(Audit.objective_id == objective_id)
    return [
        {
            "id": a.id,
            "action": a.action,
            "actor": db.get(User, a.actor_id).name,
            "objective_id": a.objective_id,
            "detail": json.loads(a.detail),
            "request_id": a.request_id,
            "occurred_at": a.occurred_at,
        }
        for a in db.scalars(query.order_by(Audit.id.desc()).offset((page - 1) * 50).limit(50))
    ]


@router.get("/review-meetings")
def meetings(user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    return [
        {
            "id": m.id,
            "title": m.title,
            "meeting_at": m.meeting_at,
            "decisions": m.decisions,
            "risks": m.risks,
            "actions": [
                {"id": a.id, "title": a.title, "owner_name": db.get(User, a.owner_id).name, "owner_id": a.owner_id, "due_date": a.due_date, "status": a.status}
                for a in db.scalars(select(ReviewAction).where(ReviewAction.meeting_id == m.id))
            ],
        }
        for m in db.scalars(select(Meeting).where(Meeting.org_id.in_(scope_ids(db, user))).order_by(Meeting.meeting_at.desc()).limit(100))
    ]


@router.post("/review-meetings", status_code=201)
def create_meeting(body: MeetingInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    if user.role not in ("Manager", "Division Head", "PMO"):
        raise HTTPException(403)
    if not db.get(Cycle, body.cycle_id):
        raise HTTPException(422, "周期不存在")
    if body.meeting_at.tzinfo is None:
        raise HTTPException(422, "会议时间需要时区")
    m = Meeting(
        **body.model_dump(exclude={"actions", "meeting_at"}),
        meeting_at=body.meeting_at.astimezone(timezone.utc).replace(tzinfo=None),
        org_id=user.org_id,
        created_by=user.id,
    )
    db.add(m)
    db.flush()
    for action in body.actions:
        owner = db.get(User, action.owner_id)
        if not owner or not owner.active or owner.org_id not in scope_ids(db, user):
            raise HTTPException(422, "行动责任人不在授权范围内")
        db.add(ReviewAction(**action.model_dump(), meeting_id=m.id))
    audit(db, user, request, "CreateMeeting", None, body.model_dump())
    return {"id": m.id}


@router.post("/review-actions/{action_id}/complete")
def finish_action(action_id: int, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    action = db.get(ReviewAction, action_id)
    if not action or action.owner_id != user.id:
        raise HTTPException(404)
    action.status = "Completed"
    audit(db, user, request, "CompleteAction", None, {"action_id": action.id})
    return {"ok": True}


@router.get("/notifications")
def notifications(user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    visible = objective_query(db, user).with_only_columns(Objective.id)
    return [
        {"id": n.id, "message": n.message, "objective_id": n.objective_id, "created_at": n.created_at}
        for n in db.scalars(
            select(Notification).where(Notification.user_id == user.id, Notification.objective_id.in_(visible)).order_by(Notification.id.desc()).limit(50)
        )
    ]
