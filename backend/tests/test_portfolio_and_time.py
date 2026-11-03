from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.business_time import business_date
from app.portfolio import BenefitInput, ClaimInput, InitiativeInput, VerificationInput


def benefit(**changes):
    return BenefitInput(
        **(
            {
                "objective_id": 1,
                "reference": "auto-2026-q4",
                "name": "自动化收益",
                "category": "cost_saving",
                "currency": "CNY",
                "unit": "元",
                "period_start": "2026-10-01",
                "period_end": "2026-12-31",
                "method": "对比同口径基准",
            }
            | changes
        )
    )


def test_business_timezone_crosses_midnight_and_month():
    assert str(business_date(datetime(2026, 10, 31, 16, 30, tzinfo=timezone.utc))) == "2026-11-01"
    assert str(business_date(datetime(2026, 10, 31, 15, 59))) == "2026-10-31"


def test_benefit_reference_normalized_and_currency_is_unit():
    b = benefit()
    assert b.reference == "AUTO-2026-Q4"
    assert b.unit == "CNY"


def test_hours_are_not_currency():
    b = benefit(category="hours_saved", currency=None)
    assert b.unit == "小时"
    with pytest.raises(ValidationError):
        benefit(category="hours_saved", currency="CNY")


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": None},
        {"period_end": "2026-01-01"},
        {"reference": "中文编号"},
        {"allocations": [{"objective_id": 1, "share": 60}, {"objective_id": 2, "share": 60}]},
        {"allocations": [{"objective_id": 1, "share": 50}, {"objective_id": 1, "share": 50}]},
        {"allocations": [{"objective_id": 1, "share": 0}]},
    ],
)
def test_invalid_benefit_and_duplicate_allocations(changes):
    with pytest.raises(ValidationError):
        benefit(**changes)


def test_partial_allocation_is_allowed_without_double_counting():
    b = benefit(allocations=[{"objective_id": 1, "share": "30.5"}, {"objective_id": 2, "share": "60.5"}])
    assert sum(a.share for a in b.allocations) == Decimal("91")


def test_qualitative_claim_has_no_invented_numeric_value():
    claim = ClaimInput(narrative="控制措施完成独立核验", evidence_id=10)
    assert claim.claimed_value is None
    verification = VerificationInput(decision="Approved", comment="与证据一致")
    assert verification.verified_value is None


def test_negative_claim_and_investment_rejected():
    with pytest.raises(ValidationError):
        ClaimInput(claimed_value="-1", narrative="invalid", evidence_id=10)
    with pytest.raises(ValidationError):
        InitiativeInput(kr_id=1, title="举措", start_date="2026-10-01", end_date="2026-12-31", currency="CNY", investment="-1")
