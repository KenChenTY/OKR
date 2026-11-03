from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, FetchedValue, ForeignKey, Index, Integer, Numeric, Unicode, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, NVARCHAR, ROWVERSION
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Entity:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class Versioned:
    row_version: Mapped[bytes] = mapped_column(ROWVERSION, nullable=False, server_default=FetchedValue())


class OrgUnit(Entity, Base):
    __tablename__ = "org_units"
    name: Mapped[str] = mapped_column(Unicode(100))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"))
    unit_type: Mapped[str] = mapped_column(Unicode(30), default="department")


class User(Entity, Base):
    __tablename__ = "users"
    subject: Mapped[str] = mapped_column(Unicode(200), unique=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    role: Mapped[str] = mapped_column(Unicode(30), default="Employee")
    org_id: Mapped[int] = mapped_column(ForeignKey("org_units.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LocalCredential(Base):
    __tablename__ = "local_credentials"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    username: Mapped[str] = mapped_column(Unicode(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Unicode(255))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)


class Cycle(Entity, Base):
    __tablename__ = "cycles"
    name: Mapped[str] = mapped_column(Unicode(100), unique=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (CheckConstraint("start_date <= end_date"),)


class Objective(Entity, Versioned, Base):
    __tablename__ = "objectives"
    code: Mapped[str] = mapped_column(Unicode(40), unique=True)
    title: Mapped[str] = mapped_column(Unicode(200))
    description: Mapped[str] = mapped_column(NVARCHAR(None))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    org_id: Mapped[int] = mapped_column(ForeignKey("org_units.id"))
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"))
    theme: Mapped[str] = mapped_column(Unicode(100))
    priority: Mapped[str] = mapped_column(Unicode(20), default="Medium")
    level: Mapped[str] = mapped_column(Unicode(20), default="department")
    visibility: Mapped[str] = mapped_column(Unicode(20), default="organization", server_default=text("N'organization'"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("objectives.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Unicode(20), default="Draft")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)
    __table_args__ = (
        CheckConstraint("start_date <= end_date"),
        CheckConstraint("status IN ('Draft','Submitted','Approved','Active','Completed','Cancelled','Archived')"),
        CheckConstraint("visibility IN ('organization','restricted')", name="ck_objective_visibility"),
        Index("ix_objectives_scope", "cycle_id", "org_id", "status"),
    )


class KeyResult(Entity, Versioned, Base):
    __tablename__ = "key_results"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), index=True)
    name: Mapped[str] = mapped_column(Unicode(200))
    value_type: Mapped[str] = mapped_column(Unicode(20))
    direction: Mapped[str] = mapped_column(Unicode(20))
    baseline: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    current_value: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    target: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    weight: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    unit: Mapped[str] = mapped_column(Unicode(30))
    currency: Mapped[str | None] = mapped_column(Unicode(3))
    evidence_source: Mapped[str] = mapped_column(Unicode(255), default="人工更新", server_default=text("N'人工更新'"))
    frequency: Mapped[str] = mapped_column(Unicode(20), default="monthly")
    confidence: Mapped[int] = mapped_column(Integer, default=70)
    last_checkin_at: Mapped[datetime | None] = mapped_column(DATETIME2(3))
    next_due: Mapped[date] = mapped_column(Date)
    severe_blocker: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("weight > 0 AND weight <= 100"), CheckConstraint("confidence BETWEEN 0 AND 100"))


class Milestone(Entity, Base):
    __tablename__ = "milestones"
    kr_id: Mapped[int] = mapped_column(ForeignKey("key_results.id"), index=True)
    name: Mapped[str] = mapped_column(Unicode(200))
    weight: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    due_date: Mapped[date] = mapped_column(Date)
    accepted_at: Mapped[datetime | None] = mapped_column(DATETIME2(3))
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (CheckConstraint("weight > 0"),)


class CheckIn(Entity, Base):
    __tablename__ = "check_ins"
    kr_id: Mapped[int] = mapped_column(ForeignKey("key_results.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    current_value: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    confidence: Mapped[int] = mapped_column(Integer)
    commentary: Mapped[str] = mapped_column(NVARCHAR(None))
    risks: Mapped[str] = mapped_column(default="")
    blockers: Mapped[str] = mapped_column(default="")
    next_action: Mapped[str] = mapped_column(default="")
    effective_at: Mapped[datetime] = mapped_column(DATETIME2(3))
    submitted_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)


class Approval(Entity, Base):
    __tablename__ = "approvals"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(Unicode(30))
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    next_assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(Unicode(20), default="Pending")
    comment: Mapped[str] = mapped_column(default="")
    decided_at: Mapped[datetime | None] = mapped_column(DATETIME2(3))
    __table_args__ = (Index("uq_approval_pending", "objective_id", unique=True, mssql_where=text("status = 'Pending'")),)


class Revision(Entity, Base):
    __tablename__ = "objective_revisions"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"))
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[str] = mapped_column(NVARCHAR(None))
    created_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)
    __table_args__ = (UniqueConstraint("objective_id", "revision"),)


class Relation(Entity, Base):
    __tablename__ = "objective_relations"
    source_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"))
    kind: Mapped[str] = mapped_column(Unicode(30))
    __table_args__ = (UniqueConstraint("source_id", "target_id", "kind"), CheckConstraint("source_id <> target_id"))


class Evidence(Entity, Base):
    __tablename__ = "evidence_versions"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), index=True)
    previous_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_versions.id"))
    name: Mapped[str] = mapped_column(Unicode(255))
    kind: Mapped[str] = mapped_column(Unicode(20))
    storage_key: Mapped[str | None] = mapped_column(Unicode(100))
    url: Mapped[str | None] = mapped_column(Unicode(2000))
    sha256: Mapped[str | None] = mapped_column(Unicode(64))
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(Unicode(20))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)


class CheckInEvidence(Base):
    __tablename__ = "check_in_evidence"
    checkin_id: Mapped[int] = mapped_column(ForeignKey("check_ins.id"), primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_versions.id"), primary_key=True)


class Meeting(Entity, Base):
    __tablename__ = "review_meetings"
    org_id: Mapped[int] = mapped_column(ForeignKey("org_units.id"))
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"))
    title: Mapped[str] = mapped_column(Unicode(200))
    meeting_at: Mapped[datetime] = mapped_column(DATETIME2(3))
    decisions: Mapped[str] = mapped_column(NVARCHAR(None))
    risks: Mapped[str] = mapped_column(default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ReviewAction(Entity, Base):
    __tablename__ = "review_actions"
    meeting_id: Mapped[int] = mapped_column(ForeignKey("review_meetings.id"))
    title: Mapped[str] = mapped_column(Unicode(200))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Unicode(20), default="Open")


class Audit(Entity, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Unicode(50))
    objective_id: Mapped[int | None] = mapped_column(ForeignKey("objectives.id"))
    detail: Mapped[str] = mapped_column(NVARCHAR(None))
    request_id: Mapped[str] = mapped_column(Unicode(64))
    occurred_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now, index=True)


class AppSession(Base):
    __tablename__ = "app_sessions"
    token_hash: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(Unicode(100))
    expires_at: Mapped[datetime] = mapped_column(DATETIME2(3))
    last_seen: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)


class LoginFlow(Base):
    __tablename__ = "login_flows"
    token_hash: Mapped[str] = mapped_column(Unicode(64), primary_key=True)
    payload: Mapped[str] = mapped_column(NVARCHAR(None))
    expires_at: Mapped[datetime] = mapped_column(DATETIME2(3))


class Idempotency(Base):
    __tablename__ = "idempotency_records"
    key: Mapped[str] = mapped_column(Unicode(200), primary_key=True)
    digest: Mapped[str] = mapped_column(Unicode(64))
    response: Mapped[str] = mapped_column(NVARCHAR(None))
    created_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)


class Job(Entity, Base):
    __tablename__ = "jobs"
    kind: Mapped[str] = mapped_column(Unicode(30))
    payload: Mapped[str] = mapped_column(NVARCHAR(None))
    dedupe_key: Mapped[str] = mapped_column(Unicode(200), unique=True)
    status: Mapped[str] = mapped_column(Unicode(20), default="Pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_run: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)
    locked_until: Mapped[datetime | None] = mapped_column(DATETIME2(3))
    lock_token: Mapped[str | None] = mapped_column(Unicode(64))
    error: Mapped[str] = mapped_column(Unicode(1000), default="")
    __table_args__ = (Index("ix_jobs_due", "status", "next_run"),)


class Notification(Entity, Base):
    __tablename__ = "notifications"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"))
    message: Mapped[str] = mapped_column(Unicode(300))
    dedupe_key: Mapped[str] = mapped_column(Unicode(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)


class ObjectiveGrant(Base):
    __tablename__ = "objective_grants"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ChangeRequest(Entity, Base):
    __tablename__ = "change_requests"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"))
    proposed: Mapped[str] = mapped_column(NVARCHAR(None))
    reason: Mapped[str] = mapped_column(NVARCHAR(None))
    stage: Mapped[str] = mapped_column(Unicode(30), default="Manager")
    status: Mapped[str] = mapped_column(Unicode(20), default="Pending")
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    next_assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decisions: Mapped[str] = mapped_column(NVARCHAR(None), default="[]")
    created_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)
    __table_args__ = (Index("uq_change_pending", "objective_id", unique=True, mssql_where=text("status = 'Pending'")),)


class Export(Entity, Base):
    __tablename__ = "exports"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("cycles.id"))
    status: Mapped[str] = mapped_column(Unicode(20), default="Pending")
    storage_key: Mapped[str] = mapped_column(Unicode(100))
    object_ids: Mapped[str] = mapped_column(NVARCHAR(None), default="[]")
    created_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)
    expires_at: Mapped[datetime] = mapped_column(DATETIME2(3))


class ScoreSnapshot(Entity, Base):
    __tablename__ = "score_snapshots"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"))
    snapshot_date: Mapped[date] = mapped_column(Date)
    formula_version: Mapped[str] = mapped_column(Unicode(20), default="1.0")
    payload: Mapped[str] = mapped_column(NVARCHAR(None))
    __table_args__ = (UniqueConstraint("objective_id", "snapshot_date"),)


class Initiative(Entity, Versioned, Base):
    __tablename__ = "initiatives"
    kr_id: Mapped[int] = mapped_column(ForeignKey("key_results.id"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(Unicode(200))
    description: Mapped[str] = mapped_column(NVARCHAR(None))
    status: Mapped[str] = mapped_column(Unicode(20), default="Planned")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    effort_hours: Mapped[Decimal] = mapped_column(Numeric(19, 4), default=0)
    investment: Mapped[Decimal] = mapped_column(Numeric(19, 4), default=0)
    currency: Mapped[str] = mapped_column(Unicode(3))
    __table_args__ = (
        CheckConstraint("start_date <= end_date"),
        CheckConstraint("effort_hours >= 0 AND investment >= 0"),
        CheckConstraint("status IN ('Planned','InProgress','Completed','Cancelled')"),
    )


class ExternalProjectLink(Entity, Base):
    __tablename__ = "external_project_links"
    initiative_id: Mapped[int] = mapped_column(ForeignKey("initiatives.id"))
    system: Mapped[str] = mapped_column(Unicode(30))
    external_id: Mapped[str] = mapped_column(Unicode(200))
    url: Mapped[str] = mapped_column(Unicode(2000))
    __table_args__ = (UniqueConstraint("initiative_id", "system", "external_id"),)


class Benefit(Entity, Base):
    __tablename__ = "benefits"
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), index=True)
    kr_id: Mapped[int | None] = mapped_column(ForeignKey("key_results.id"), index=True)
    reference: Mapped[str] = mapped_column(Unicode(100), unique=True)
    name: Mapped[str] = mapped_column(Unicode(200))
    category: Mapped[str] = mapped_column(Unicode(30))
    unit: Mapped[str] = mapped_column(Unicode(30))
    currency: Mapped[str | None] = mapped_column(Unicode(3))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(NVARCHAR(None))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (CheckConstraint("period_start <= period_end"),)


class BenefitAllocation(Base):
    __tablename__ = "benefit_allocations"
    benefit_id: Mapped[int] = mapped_column(ForeignKey("benefits.id"), primary_key=True)
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), primary_key=True)
    share: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    __table_args__ = (CheckConstraint("share > 0 AND share <= 100"),)


class BenefitClaim(Entity, Base):
    __tablename__ = "benefit_claims"
    benefit_id: Mapped[int] = mapped_column(ForeignKey("benefits.id"), index=True)
    claimed_value: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    narrative: Mapped[str] = mapped_column(NVARCHAR(None))
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence_versions.id"))
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)
    status: Mapped[str] = mapped_column(Unicode(20), default="Pending")
    __table_args__ = (
        CheckConstraint("claimed_value IS NULL OR claimed_value >= 0"),
        Index("uq_benefit_pending_claim", "benefit_id", unique=True, mssql_where=text("status = 'Pending'")),
    )


class BenefitVerification(Entity, Base):
    __tablename__ = "benefit_verifications"
    claim_id: Mapped[int] = mapped_column(ForeignKey("benefit_claims.id"), unique=True)
    verified_value: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(Unicode(20))
    comment: Mapped[str] = mapped_column(NVARCHAR(None))
    verified_at: Mapped[datetime] = mapped_column(DATETIME2(3), default=now)
    __table_args__ = (CheckConstraint("verified_value IS NULL OR verified_value >= 0"),)
