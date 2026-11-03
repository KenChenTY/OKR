from datetime import date, datetime
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from app.domain import HealthPolicy, due_after, health, planned_progress, progress, weighted_score, would_cycle
from app.schemas import KRInput, ObjectiveInput


@pytest.mark.parametrize(
    "baseline,current,target,raw,clipped",
    [
        (100, 150, 200, 50, 50),
        (10, 7, 4, 50, 50),
        (0, 120, 100, 120, 100),
        (100, 80, 200, -20, 0),
        (0, 0, 10, 0, 0),
        (10, 0, 0, 100, 100),
    ],
)
def test_progress_examples(baseline, current, target, raw, clipped):
    assert progress(D(baseline), D(current), D(target)) == (D(raw), D(clipped))


def test_equal_target_rejected():
    with pytest.raises(ValueError):
        progress(D(5), D(10), D(5))


def test_weighted_and_empty_score():
    assert weighted_score([(D(100), D(25)), (D(0), D(75))]) == D(25)
    assert weighted_score([]) is None


@pytest.mark.parametrize(
    "anchor,frequency,after,expected",
    [
        (date(2026, 1, 31), "monthly", date(2026, 1, 31), date(2026, 2, 28)),
        (date(2026, 1, 31), "monthly", date(2026, 2, 28), date(2026, 3, 31)),
        (date(2028, 1, 31), "monthly", date(2028, 1, 31), date(2028, 2, 29)),
        (date(2026, 12, 31), "monthly", date(2027, 1, 31), date(2027, 2, 28)),
        (date(2026, 1, 1), "biweekly", date(2026, 1, 20), date(2026, 1, 29)),
        (date(2026, 1, 1), "weekly", date(2026, 1, 8), date(2026, 1, 15)),
    ],
)
def test_frequency_anchors(anchor, frequency, after, expected):
    assert due_after(anchor, frequency, after) == expected


@pytest.mark.parametrize(
    "value,planned,confidence,last,due,severe,expected",
    [
        (50, 50, 80, None, date(2026, 10, 31), False, "Gray"),
        (50, 50, 80, datetime(2026, 10, 1), date(2026, 10, 26), False, "Gray"),
        (50, 50, 80, datetime(2026, 10, 1), date(2026, 10, 27), False, "Green"),
        (50, 71, 80, datetime(2026, 10, 1), date(2026, 10, 31), False, "Red"),
        (50, 61, 80, datetime(2026, 10, 1), date(2026, 10, 31), False, "Amber"),
        (80, 50, 39, datetime(2026, 10, 1), date(2026, 10, 31), False, "Red"),
        (80, 50, 69, datetime(2026, 10, 1), date(2026, 10, 31), False, "Amber"),
        (80, 50, 90, datetime(2026, 10, 1), date(2026, 10, 31), True, "Red"),
    ],
)
def test_health(value, planned, confidence, last, due, severe, expected):
    assert health(value, planned, confidence, last, due, date(2026, 10, 30), severe) == expected


def test_alignment_cycles_and_shared_parent():
    assert would_cycle([(1, 2), (2, 3)], 3, 1)
    assert would_cycle([], 1, 1)
    assert not would_cycle([(1, 3), (2, 3)], 4, 2)


def test_planned_progress_has_no_float_threshold_drift():
    today = date(2026, 10, 5)
    planned = planned_progress(date(2026, 10, 1), date(2026, 10, 11), today)
    assert planned == D("40")
    assert health(D("20"), planned, 80, datetime(2026, 10, 4), today, today) == "Amber"


def test_health_policy_is_configurable():
    today = date(2026, 10, 5)
    policy = HealthPolicy(grace_days=0, red_confidence=30, amber_confidence=60, red_lag=30, amber_lag=15)
    assert health(20, 40, 80, datetime(2026, 10, 4), date(2026, 10, 4), today, policy=policy) == "Gray"


@pytest.mark.parametrize(
    "patch",
    [
        {"target": "0"},
        {"direction": "decrease", "target": "100"},
        {"value_type": "currency"},
        {"value_type": "count", "target": "2.5"},
        {"weight": "0"},
        {"value_type": "milestone", "milestones": []},
    ],
)
def test_invalid_kr(patch):
    with pytest.raises(ValidationError):
        KRInput(**({"name": "KR", "unit": "次", "weight": "100", "baseline": "0", "target": "100"} | patch))


def test_milestone_weights_and_direction():
    body = KRInput(name="交付", unit="%", value_type="milestone", weight="100", milestones=[{"name": "上线", "weight": "100", "due_date": "2026-12-01"}])
    assert body.baseline == 0 and body.target == 100


def test_objective_dates():
    with pytest.raises(ValidationError):
        ObjectiveInput(title="test", description="test", theme="test", cycle_id=1, start_date="2026-12-01", end_date="2026-01-01")
