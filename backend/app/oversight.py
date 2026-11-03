"""Quarterly review plans and access-scoped organizational analytics."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import CheckConstraint, ForeignKey, Unicode, select
from sqlalchemy.dialects.mssql import DATETIME2, NVARCHAR
from sqlalchemy.orm import Mapped, Session, mapped_column

from .business_time import today
from .db import Base, get_db
from .models import Entity, Objective, OrgUnit, User, now
from .schemas import Input
from .security import current_user, scope_ids
from .services import audit, get_objective, lock, objective_query, objective_view

router = APIRouter(prefix="/api/v1", tags=["reviews and analytics"])


class QuarterlyReview(Entity, Base):
    __tablename__ = "quarterly_reviews"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), unique=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date]
    status: Mapped[str] = mapped_column(Unicode(20), default="Pending")
    summary: Mapped[str] = mapped_column(NVARCHAR(None), default="")
    lessons: Mapped[str] = mapped_column(NVARCHAR(None), default="")
    next_steps: Mapped[str] = mapped_column(NVARCHAR(None), default="")
    completed_at: Mapped[object | None] = mapped_column(DATETIME2(3))
    __table_args__ = (CheckConstraint("status IN ('Pending','Completed')"),)


class StrategicAssessment(Base):
    __tablename__ = "strategic_assessments"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), primary_key=True)
    score: Mapped[int]
    rationale: Mapped[str] = mapped_column(NVARCHAR(None))
    assessed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assessed_at: Mapped[object] = mapped_column(DATETIME2(3), default=now)
    __table_args__ = (CheckConstraint("score >= 0 AND score <= 100"),)


class ReviewPlan(Input):
    objective_id: int
    reviewer_id: int
    due_date: date


class ReviewCompletion(Input):
    summary: str = Field(min_length=1, max_length=10000)
    lessons: str = Field(min_length=1, max_length=10000)
    next_steps: str = Field(min_length=1, max_length=10000)


class AssessmentInput(Input):
    score: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=5000)


def manager_scope(db, user, obj):
    if user.role not in ("Manager", "Division Head", "PMO") or obj.org_id not in scope_ids(db, user):
        raise HTTPException(403, "没有此组织的评审管理权限")


@router.get("/quarterly-reviews")
def reviews(cycle_id: int | None = None, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    visible = objective_query(db, user)
    if cycle_id:
        visible = visible.where(Objective.cycle_id == cycle_id)
    rows = db.scalars(
        select(QuarterlyReview).where(QuarterlyReview.objective_id.in_(visible.with_only_columns(Objective.id))).order_by(QuarterlyReview.due_date)
    )
    return [
        {
            "id": r.id,
            "objective_id": r.objective_id,
            "objective_title": db.get(Objective, r.objective_id).title,
            "reviewer_id": r.reviewer_id,
            "reviewer": db.get(User, r.reviewer_id).name,
            "due_date": r.due_date,
            "status": r.status,
            "overdue": r.status == "Pending" and r.due_date < today(),
            "summary": r.summary,
            "lessons": r.lessons,
            "next_steps": r.next_steps,
            "completed_at": r.completed_at,
        }
        for r in rows
    ]


@router.post("/quarterly-reviews", status_code=201)
def plan_review(body: ReviewPlan, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    obj = get_objective(db, user, body.objective_id, True)
    manager_scope(db, user, obj)
    lock(db, f"quarterly-review:{obj.id}")
    if obj.status not in ("Approved", "Active", "Completed"):
        raise HTTPException(409, "仅已批准、执行中或已完成目标可安排复盘")
    reviewer = db.get(User, body.reviewer_id)
    if not reviewer or not reviewer.active or reviewer.id == obj.owner_id:
        raise HTTPException(422, "复盘需指定独立且有效的评审人")
    manager_scope(db, reviewer, obj)
    get_objective(db, reviewer, obj.id)
    if body.due_date < obj.start_date:
        raise HTTPException(422, "复盘截止日期不能早于目标开始日期")
    record = db.scalar(select(QuarterlyReview).where(QuarterlyReview.objective_id == obj.id))
    if record and record.status == "Completed":
        raise HTTPException(409, "已完成复盘不可覆盖")
    if record:
        record.reviewer_id, record.due_date = body.reviewer_id, body.due_date
    else:
        record = QuarterlyReview(**body.model_dump())
        db.add(record)
    db.flush()
    audit(db, user, request, "PlanQuarterlyReview", obj.id, body.model_dump())
    return {"id": record.id}


@router.post("/quarterly-reviews/{review_id}/complete")
def complete_review(
    review_id: int,
    body: ReviewCompletion,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    record = db.get(QuarterlyReview, review_id)
    if not record:
        raise HTTPException(404)
    obj = get_objective(db, user, record.objective_id, True)
    lock(db, f"quarterly-review:{record.objective_id}")
    db.refresh(record)
    manager_scope(db, user, obj)
    if user.id != record.reviewer_id or user.id == obj.owner_id:
        raise HTTPException(403)
    if record.status != "Pending" or obj.status not in ("Active", "Completed"):
        raise HTTPException(409, "目标需开始执行，且复盘尚未完成")
    for name, value in body.model_dump().items():
        setattr(record, name, value)
    record.status, record.completed_at = "Completed", now()
    audit(db, user, request, "CompleteQuarterlyReview", obj.id, body.model_dump())
    return {"ok": True}


@router.put("/objectives/{objective_id}/strategic-assessment")
def assess(
    objective_id: int,
    body: AssessmentInput,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    obj = get_objective(db, user, objective_id, True)
    manager_scope(db, user, obj)
    lock(db, f"strategy:{obj.id}")
    if obj.status in ("Cancelled", "Archived"):
        raise HTTPException(409)
    record = db.get(StrategicAssessment, obj.id)
    before = {"score": record.score, "rationale": record.rationale} if record else None
    if not record:
        record = StrategicAssessment(objective_id=obj.id)
        db.add(record)
    record.score, record.rationale = body.score, body.rationale
    record.assessed_by, record.assessed_at = user.id, now()
    audit(db, user, request, "AssessStrategicValue", obj.id, {"before": before, "after": body.model_dump()})
    return {"ok": True}


def mean_score(scores):
    return str((sum(scores) / len(scores)).quantize(Decimal("0.01"))) if scores else None


def analytics_data(db, user, cycle_id):
    query = objective_query(db, user)
    if cycle_id:
        query = query.where(Objective.cycle_id == cycle_id)
    objects = list(db.scalars(query))
    ids = {o.id for o in objects}
    effective = [o for o in objects if o.status not in ("Draft", "Cancelled", "Archived")]
    units = {o.id: o for o in db.scalars(select(OrgUnit))}
    reviews_ = list(db.scalars(select(QuarterlyReview).where(QuarterlyReview.objective_id.in_(ids))))
    departments, divisions = {}, {}
    for obj in objects:
        view = objective_view(db, obj) if obj.status not in ("Draft", "Cancelled", "Archived") else None

        def ancestor(kind):
            unit, seen = units.get(obj.org_id), set()
            while unit and unit.id not in seen:
                if unit.unit_type == kind:
                    return unit
                seen.add(unit.id)
                unit = units.get(unit.parent_id)
            return units.get(obj.org_id)

        for kind, groups in (("division", divisions), ("department", departments)):
            unit = ancestor(kind)
            row = groups.setdefault(
                unit.id,
                {
                    "id": unit.id,
                    "name": unit.name,
                    "count": 0,
                    "scores": [],
                    "health": {k: 0 for k in ("Green", "Amber", "Red", "Gray")},
                    "statuses": {},
                    "overdue_reviews": 0,
                },
            )
            row["count"] += 1
            row["statuses"][obj.status] = row["statuses"].get(obj.status, 0) + 1
            if view and view["raw_score"] is not None:
                row["scores"].append(Decimal(view["raw_score"]))
            for key, value in (view["health_counts"] if view else {}).items():
                row["health"][key] += value
            row["overdue_reviews"] += sum(r.objective_id == obj.id and r.status == "Pending" and r.due_date < today() for r in reviews_) if view else 0

    def finish(groups):
        result = []
        for row in groups.values():
            row["achievement"] = mean_score(row.pop("scores"))
            total = sum(row["health"].values())
            row["risk_concentration"] = str((Decimal(row["health"]["Red"] + row["health"]["Amber"]) * 100 / total).quantize(Decimal("0.01"))) if total else None
            result.append(row)
        return sorted(result, key=lambda r: r["id"])

    assessments = list(db.scalars(select(StrategicAssessment).where(StrategicAssessment.objective_id.in_({o.id for o in effective}))))
    return {
        "divisions": finish(divisions),
        "departments": finish(departments),
        "unplanned_reviews": sum(not any(r.objective_id == o.id for r in reviews_) for o in effective),
        "strategic_value": mean_score([Decimal(a.score) for a in assessments]),
        "assessed_count": len(assessments),
        "effective_count": len(effective),
        "assessments": [
            {"objective_id": a.objective_id, "score": a.score, "rationale": a.rationale, "assessed_by": a.assessed_by, "assessed_at": a.assessed_at}
            for a in assessments
        ],
    }


@router.get("/dashboards/organization")
def analytics(cycle_id: int | None = None, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    return analytics_data(db, user, cycle_id)
