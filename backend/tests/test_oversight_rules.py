from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.oversight import AssessmentInput, ReviewCompletion, mean_score
from app.api import EvidenceSourceInput


def test_average_preserves_unassessed_as_missing_and_zero_as_score():
    assert mean_score([]) is None
    assert mean_score([Decimal(0), Decimal(100)]) == "50.00"
    assert mean_score([Decimal("33.333"), Decimal("66.667")]) == "50.00"


def test_strategy_requires_rationale_and_bounded_score():
    assert AssessmentInput(score=0, rationale="No strategic contribution").score == 0
    for score, rationale in [(101, "Reason"), (-1, "Reason"), (50, " ")]:
        with pytest.raises(ValidationError):
            AssessmentInput(score=score, rationale=rationale)


def test_retrospective_cannot_omit_lessons_or_next_steps():
    with pytest.raises(ValidationError):
        ReviewCompletion(summary="Reviewed", lessons="", next_steps="Next quarter")
    with pytest.raises(ValidationError):
        EvidenceSourceInput(evidence_source=" ")
