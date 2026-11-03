from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ObjectiveInput(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    cycle_id: int
    theme: str = Field(min_length=1, max_length=100)
    priority: Literal["Low", "Medium", "High"] = "Medium"
    level: Literal["corporate", "division", "department", "team", "personal"] = "department"
    visibility: Literal["organization", "restricted"] = "organization"
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def dates(self):
        if self.start_date > self.end_date:
            raise ValueError("结束日期不得早于开始日期")
        return self


class MilestoneInput(Input):
    name: str = Field(min_length=1, max_length=200)
    weight: Decimal = Field(gt=0, le=100, max_digits=9, decimal_places=4)
    due_date: date


class KRInput(Input):
    name: str = Field(min_length=1, max_length=200)
    value_type: Literal["number", "count", "percentage", "currency", "milestone"] = "number"
    direction: Literal["increase", "decrease"] = "increase"
    baseline: Decimal = Field(default=Decimal(0), max_digits=19, decimal_places=4)
    target: Decimal = Field(default=Decimal(100), max_digits=19, decimal_places=4)
    weight: Decimal = Field(gt=0, le=100, max_digits=9, decimal_places=4)
    unit: str = Field(min_length=1, max_length=30)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    frequency: Literal["weekly", "biweekly", "monthly"] = "monthly"
    evidence_source: str = Field(default="人工更新", min_length=1, max_length=255)
    milestones: list[MilestoneInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def metric(self):
        if self.value_type == "milestone":
            if not self.milestones or sum(m.weight for m in self.milestones) != 100:
                raise ValueError("里程碑权重之和必须为100")
            self.baseline, self.target, self.direction = Decimal(0), Decimal(100), "increase"
        else:
            if self.milestones:
                raise ValueError("数值型KR不能填写里程碑")
            if self.target == self.baseline or (self.direction == "increase") != (self.target > self.baseline):
                raise ValueError("基线和目标必须符合增长或下降方向")
        if self.value_type == "currency" and not self.currency:
            raise ValueError("货币类KR必须填写币种")
        if self.value_type == "count" and any(v != v.to_integral_value() for v in (self.baseline, self.target)):
            raise ValueError("计数必须为整数")
        return self


class CheckInInput(Input):
    current_value: Decimal = Field(max_digits=19, decimal_places=4)
    confidence: int = Field(ge=0, le=100)
    commentary: str = Field(min_length=1, max_length=5000)
    risks: str = Field(default="", max_length=5000)
    blockers: str = Field(default="", max_length=5000)
    next_action: str = Field(default="", max_length=5000)
    severe_blocker: bool = False
    effective_at: datetime
    evidence_version_ids: list[int] = Field(default_factory=list, max_length=20)


class DecisionInput(Input):
    decision: Literal["Approved", "Rejected"]
    comment: str = Field(min_length=1, max_length=2000)


class TransitionInput(Input):
    action: Literal["withdraw", "activate", "request_completion", "complete", "cancel", "archive"]
    reason: str = Field(min_length=1, max_length=2000)


class RelationInput(Input):
    target_id: int
    kind: Literal["contributes_to", "depends_on", "parent"]


class LinkInput(Input):
    objective_id: int
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(max_length=2000)
    previous_id: int | None = None


class ActionInput(Input):
    title: str = Field(min_length=1, max_length=200)
    owner_id: int
    due_date: date


class MeetingInput(Input):
    cycle_id: int
    title: str = Field(min_length=1, max_length=200)
    meeting_at: datetime
    decisions: str = Field(min_length=1, max_length=10000)
    risks: str = Field(default="", max_length=5000)
    actions: list[ActionInput] = Field(default_factory=list, max_length=50)
