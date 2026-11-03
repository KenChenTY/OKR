from datetime import date
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .business_time import today
from .db import get_db
from .models import Benefit, BenefitAllocation, BenefitClaim, BenefitVerification, ExternalProjectLink, Initiative, KeyResult, Objective, User
from .schemas import Input
from .security import current_user, require_owner, scope_ids
from .services import audit, check_version, etag, get_objective, lock, objective_query, validate_evidence

router = APIRouter(prefix="/api/v1", tags=["portfolio"])


class InitiativeInput(Input):
    kr_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    start_date: date
    end_date: date
    effort_hours: Decimal = Field(default=Decimal(0), ge=0, max_digits=19, decimal_places=4)
    investment: Decimal = Field(default=Decimal(0), ge=0, max_digits=19, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def dates(self):
        if self.start_date > self.end_date:
            raise ValueError("举措开始日期不得晚于结束日期")
        return self


class InitiativeStatus(Input):
    status: Literal["InProgress", "Completed", "Cancelled"]
    reason: str = Field(min_length=1, max_length=2000)


class ProjectInput(Input):
    system: Literal["Jira", "Azure DevOps", "ServiceNow", "Planner"]
    external_id: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=2000)


class AllocationInput(Input):
    objective_id: int
    share: Decimal = Field(gt=0, le=100, max_digits=9, decimal_places=4)


class BenefitInput(Input):
    objective_id: int
    kr_id: int | None = None
    reference: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    name: str = Field(min_length=1, max_length=200)
    category: Literal["cost_saving", "hours_saved", "revenue", "risk_reduction", "compliance_improvement"]
    unit: str = Field(min_length=1, max_length=30)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    period_start: date
    period_end: date
    method: str = Field(min_length=1, max_length=5000)
    allocations: list[AllocationInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid_benefit(self):
        self.reference = self.reference.upper()
        if self.period_start > self.period_end:
            raise ValueError("收益期间无效")
        if self.category in ("cost_saving", "revenue"):
            if not self.currency:
                raise ValueError("货币收益必须指定币种")
            self.unit = self.currency
        elif self.currency:
            raise ValueError("非货币收益不能填写币种")
        if self.category == "hours_saved":
            self.unit = "小时"
        if self.allocations:
            if len({a.objective_id for a in self.allocations}) != len(self.allocations):
                raise ValueError("分摊目标不能重复")
            if sum(a.share for a in self.allocations) > 100:
                raise ValueError("分摊比例合计不能超过100%")
        return self


class ClaimInput(Input):
    claimed_value: Decimal | None = Field(default=None, ge=0, max_digits=19, decimal_places=4)
    narrative: str = Field(min_length=1, max_length=5000)
    evidence_id: int


class BenefitKRInput(Input):
    kr_id: int


@router.patch("/benefits/{benefit_id}/key-result")
def assign_benefit_kr(benefit_id: int, body: BenefitKRInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    lock(db, f"benefit:{benefit_id}")
    benefit = db.get(Benefit, benefit_id)
    if not benefit:
        raise HTTPException(404)
    obj = get_objective(db, user, benefit.objective_id)
    if user.role != "PMO":
        require_owner(user, obj)
    if benefit.kr_id is not None:
        raise HTTPException(409, "收益已关联KR，不可覆盖历史关系")
    kr = db.get(KeyResult, body.kr_id)
    if not kr or kr.objective_id != obj.id:
        raise HTTPException(422, "收益必须关联当前目标下的关键结果")
    benefit.kr_id = kr.id
    audit(db, user, request, "AssignBenefitKR", obj.id, {"benefit_id": benefit.id, "kr_id": kr.id})
    return {"ok": True}


class VerificationInput(Input):
    decision: Literal["Approved", "Rejected"]
    verified_value: Decimal | None = Field(default=None, ge=0, max_digits=19, decimal_places=4)
    comment: str = Field(min_length=1, max_length=3000)


def initiative_view(db, item):
    kr = db.get(KeyResult, item.kr_id)
    obj = db.get(Objective, kr.objective_id)
    return {
        "id": item.id,
        "kr_id": item.kr_id,
        "kr_name": kr.name,
        "objective_id": obj.id,
        "objective_title": obj.title,
        "title": item.title,
        "description": item.description,
        "owner_id": item.owner_id,
        "status": item.status,
        "start_date": item.start_date,
        "end_date": item.end_date,
        "actual_end_date": item.actual_end_date,
        "effort_hours": str(item.effort_hours),
        "investment": str(item.investment),
        "currency": item.currency,
        "etag": etag(item),
        "links": [
            {"system": p.system, "external_id": p.external_id, "url": p.url}
            for p in db.scalars(select(ExternalProjectLink).where(ExternalProjectLink.initiative_id == item.id))
        ],
    }


@router.get("/initiatives")
def initiatives(cycle_id: int | None = None, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    visible = objective_query(db, user)
    if cycle_id:
        visible = visible.where(Objective.cycle_id == cycle_id)
    query = select(Initiative).join(KeyResult, KeyResult.id == Initiative.kr_id).where(KeyResult.objective_id.in_(visible.with_only_columns(Objective.id)))
    return [initiative_view(db, i) for i in db.scalars(query.order_by(Initiative.id.desc()).limit(200))]


@router.post("/initiatives", status_code=201)
def create_initiative(
    body: InitiativeInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    kr = db.get(KeyResult, body.kr_id)
    if not kr:
        raise HTTPException(404)
    obj = get_objective(db, user, kr.objective_id, True)
    require_owner(user, obj)
    if obj.status not in ("Draft", "Approved", "Active"):
        raise HTTPException(409, "当前目标状态不能新增举措")
    item = Initiative(**body.model_dump(), owner_id=user.id)
    db.add(item)
    db.flush()
    db.refresh(item)
    audit(db, user, request, "CreateInitiative", obj.id, body.model_dump())
    return initiative_view(db, item)


@router.post("/initiatives/{initiative_id}/transitions")
def initiative_transition(
    initiative_id: int,
    body: InitiativeStatus,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    item = db.get(Initiative, initiative_id)
    if not item:
        raise HTTPException(404)
    kr = db.get(KeyResult, item.kr_id)
    obj = get_objective(db, user, kr.objective_id, True)
    require_owner(user, obj)
    db.refresh(item)
    check_version(item, request)
    allowed = {"Planned": {"InProgress", "Cancelled"}, "InProgress": {"Completed", "Cancelled"}}
    if obj.status != "Active" or body.status not in allowed.get(item.status, set()):
        raise HTTPException(409, "目标未开始执行或举措状态不允许该操作")
    before = item.status
    item.status = body.status
    if body.status == "Completed":
        item.actual_end_date = today()
    audit(db, user, request, "UpdateInitiative", obj.id, {"id": item.id, "before": before, "after": body.status, "reason": body.reason})
    db.flush()
    db.refresh(item)
    return initiative_view(db, item)


@router.patch("/initiatives/{initiative_id}")
def edit_initiative(
    initiative_id: int,
    body: InitiativeInput,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    item = db.get(Initiative, initiative_id)
    if not item:
        raise HTTPException(404)
    obj = get_objective(db, user, db.get(KeyResult, item.kr_id).objective_id, True)
    require_owner(user, obj)
    db.refresh(item)
    check_version(item, request)
    if body.kr_id != item.kr_id or item.status not in ("Planned", "InProgress") or obj.status not in ("Draft", "Approved", "Active"):
        raise HTTPException(409, "举措已终止或尝试变更关联KR")
    before = initiative_view(db, item)
    for key, value in body.model_dump().items():
        setattr(item, key, value)
    audit(db, user, request, "EditInitiative", obj.id, {"before": before, "after": body.model_dump()})
    db.flush()
    db.refresh(item)
    return initiative_view(db, item)


@router.post("/initiatives/{initiative_id}/links", status_code=201)
def project_link(
    initiative_id: int,
    body: ProjectInput,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    item = db.get(Initiative, initiative_id)
    if not item:
        raise HTTPException(404)
    obj = get_objective(db, user, db.get(KeyResult, item.kr_id).objective_id, True)
    require_owner(user, obj)
    if obj.status in ("Completed", "Cancelled", "Archived"):
        raise HTTPException(409, "终态目标的项目链接不可修改")
    url = urlparse(body.url)
    if url.scheme != "https" or url.hostname not in {h.strip().lower() for h in settings().project_link_hosts.split(",")} or url.username or url.password:
        raise HTTPException(422, "项目链接必须属于已配置的HTTPS域名白名单")
    db.add(ExternalProjectLink(**body.model_dump(), initiative_id=item.id))
    audit(db, user, request, "LinkProject", obj.id, {"initiative_id": item.id, **body.model_dump()})
    return {"ok": True}


def benefit_view(db, benefit):
    claims = list(db.scalars(select(BenefitClaim).where(BenefitClaim.benefit_id == benefit.id).order_by(BenefitClaim.id.desc())))
    verified = db.scalar(
        select(BenefitVerification)
        .join(BenefitClaim, BenefitClaim.id == BenefitVerification.claim_id)
        .where(BenefitClaim.benefit_id == benefit.id, BenefitVerification.decision == "Approved")
        .order_by(BenefitVerification.id.desc())
        .limit(1)
    )
    allocations = list(db.scalars(select(BenefitAllocation).where(BenefitAllocation.benefit_id == benefit.id)))
    return {
        "id": benefit.id,
        "objective_id": benefit.objective_id,
        "kr_id": benefit.kr_id,
        "kr_name": db.get(KeyResult, benefit.kr_id).name if benefit.kr_id else None,
        "objective_title": db.get(Objective, benefit.objective_id).title,
        "reference": benefit.reference,
        "name": benefit.name,
        "category": benefit.category,
        "unit": benefit.unit,
        "currency": benefit.currency,
        "period_start": benefit.period_start,
        "period_end": benefit.period_end,
        "method": benefit.method,
        "created_by": benefit.created_by,
        "claimed_value": str(claims[0].claimed_value) if claims and claims[0].claimed_value is not None else None,
        "verified_value": str(verified.verified_value) if verified and verified.verified_value is not None else None,
        "has_verified": verified is not None,
        "allocations": [{"objective_id": a.objective_id, "share": str(a.share)} for a in allocations],
        "claims": [
            {
                "id": c.id,
                "value": str(c.claimed_value) if c.claimed_value is not None else None,
                "narrative": c.narrative,
                "evidence_id": c.evidence_id,
                "submitted_by": c.submitted_by,
                "submitted_at": c.submitted_at,
                "status": c.status,
                "verification": next(
                    (
                        {
                            "decision": v.decision,
                            "value": str(v.verified_value) if v.verified_value is not None else None,
                            "comment": v.comment,
                            "reviewer": db.get(User, v.reviewer_id).name,
                            "at": v.verified_at,
                        }
                        for v in db.scalars(select(BenefitVerification).where(BenefitVerification.claim_id == c.id))
                    ),
                    None,
                ),
            }
            for c in claims
        ],
    }


@router.get("/benefits")
def benefits(cycle_id: int | None = None, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    visible = objective_query(db, user)
    if cycle_id:
        visible = visible.where(Objective.cycle_id == cycle_id)
    return [
        benefit_view(db, b)
        for b in db.scalars(select(Benefit).where(Benefit.objective_id.in_(visible.with_only_columns(Objective.id))).order_by(Benefit.id.desc()).limit(200))
    ]


@router.post("/benefits", status_code=201)
def create_benefit(body: BenefitInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    obj = get_objective(db, user, body.objective_id, True)
    kr = db.get(KeyResult, body.kr_id) if body.kr_id else None
    if not kr or kr.objective_id != obj.id:
        raise HTTPException(422, "收益必须关联当前目标下的关键结果")
    if user.role != "PMO":
        require_owner(user, obj)
    if obj.status not in ("Approved", "Active", "Completed"):
        raise HTTPException(409, "收益需关联已批准、执行中或已完成的目标")
    if body.allocations and any(a.objective_id != obj.id for a in body.allocations) and user.role != "PMO":
        raise HTTPException(403, "跨目标分摊由PMO统一登记")
    for a in body.allocations:
        get_objective(db, user, a.objective_id)
    benefit = Benefit(**body.model_dump(exclude={"allocations"}), created_by=user.id)
    db.add(benefit)
    db.flush()
    allocations = body.allocations or [AllocationInput(objective_id=obj.id, share=Decimal(100))]
    for a in allocations:
        db.add(BenefitAllocation(benefit_id=benefit.id, **a.model_dump()))
    audit(db, user, request, "CreateBenefit", obj.id, body.model_dump())
    db.flush()
    return benefit_view(db, benefit)


@router.post("/benefits/{benefit_id}/claims", status_code=201)
def claim_benefit(
    benefit_id: int, body: ClaimInput, request: Request, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")
):
    benefit = db.get(Benefit, benefit_id)
    if not benefit:
        raise HTTPException(404)
    obj = get_objective(db, user, benefit.objective_id, True)
    require_owner(user, obj)
    lock(db, f"benefit:{benefit_id}")
    if obj.status not in ("Approved", "Active", "Completed"):
        raise HTTPException(409, "当前目标状态不可申报收益")
    if db.scalar(select(BenefitClaim.id).where(BenefitClaim.benefit_id == benefit.id, BenefitClaim.status == "Pending")):
        raise HTTPException(409, "已有待核验的收益申报")
    if benefit.category in ("cost_saving", "revenue", "hours_saved") and body.claimed_value is None:
        raise HTTPException(422, "量化收益必须填写申报值")
    validate_evidence(db, obj.id, [body.evidence_id])
    claim = BenefitClaim(**body.model_dump(), benefit_id=benefit.id, submitted_by=user.id)
    db.add(claim)
    db.flush()
    audit(db, user, request, "ClaimBenefit", obj.id, {"claim_id": claim.id, **body.model_dump()})
    return {"id": claim.id, "status": claim.status}


@router.post("/benefit-claims/{claim_id}/verifications", status_code=201)
def verify_benefit(
    claim_id: int,
    body: VerificationInput,
    request: Request,
    user: User = Depends(current_user, scope="function"),
    db: Session = Depends(get_db, scope="function"),
):
    claim = db.get(BenefitClaim, claim_id)
    if not claim:
        raise HTTPException(404)
    benefit = db.get(Benefit, claim.benefit_id)
    obj = get_objective(db, user, benefit.objective_id, True)
    lock(db, f"benefit:{benefit.id}")
    db.refresh(claim)
    if user.role not in ("Manager", "Division Head", "PMO") or user.id in (claim.submitted_by, obj.owner_id) or obj.org_id not in scope_ids(db, user):
        raise HTTPException(403, "收益需由授权范围内的独立审核人核验")
    if claim.status != "Pending":
        raise HTTPException(409, "该申报已经核验")
    validate_evidence(db, obj.id, [claim.evidence_id])
    if body.decision == "Approved" and benefit.category in ("cost_saving", "revenue", "hours_saved") and body.verified_value is None:
        raise HTTPException(422, "量化收益核验必须填写核验值")
    data = body.model_dump()
    if body.decision == "Rejected":
        data["verified_value"] = None
    db.add(BenefitVerification(**data, claim_id=claim.id, reviewer_id=user.id))
    claim.status = body.decision
    audit(db, user, request, "VerifyBenefit", obj.id, {"claim_id": claim.id, **data})
    return {"status": claim.status}


@router.get("/dashboards/portfolio")
def portfolio(cycle_id: int | None = None, user: User = Depends(current_user, scope="function"), db: Session = Depends(get_db, scope="function")):
    visible = objective_query(db, user)
    if cycle_id:
        visible = visible.where(Objective.cycle_id == cycle_id)
    ids = set(db.scalars(visible.with_only_columns(Objective.id)))
    initiatives_ = list(
        db.scalars(
            select(Initiative).join(KeyResult, KeyResult.id == Initiative.kr_id).where(KeyResult.objective_id.in_(ids), Initiative.status != "Cancelled")
        )
    )
    investment: dict[str, Decimal] = {}
    for item in initiatives_:
        investment[item.currency] = investment.get(item.currency, Decimal(0)) + item.investment
    totals: dict[tuple[str, str], Decimal] = {}
    qualitative = []
    for benefit in db.scalars(select(Benefit).where(Benefit.objective_id.in_(ids))):
        view = benefit_view(db, benefit)
        if not view["has_verified"]:
            continue
        if benefit.category in ("risk_reduction", "compliance_improvement"):
            qualitative.append({"id": benefit.id, "name": benefit.name, "category": benefit.category, "value": view["verified_value"], "unit": benefit.unit})
            continue
        share = sum(
            (a.share for a in db.scalars(select(BenefitAllocation).where(BenefitAllocation.benefit_id == benefit.id, BenefitAllocation.objective_id.in_(ids)))),
            Decimal(0),
        )
        key = (benefit.category, benefit.currency or benefit.unit)
        totals[key] = totals.get(key, Decimal(0)) + Decimal(view["verified_value"]) * share / 100
    return {
        "initiative_count": len(initiatives_),
        "completed_count": sum(i.status == "Completed" for i in initiatives_),
        "effort_hours": str(sum((i.effort_hours for i in initiatives_), Decimal(0))),
        "investment": [{"currency": c, "value": str(v)} for c, v in sorted(investment.items())],
        "verified_benefits": [{"category": k[0], "unit": k[1], "value": str(v)} for k, v in sorted(totals.items())],
        "qualitative": qualitative,
    }
