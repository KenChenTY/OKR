import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


def progress(baseline: Decimal, current: Decimal, target: Decimal):
    if target == baseline:
        raise ValueError("目标值不能等于基线")
    raw = (current - baseline) / (target - baseline) * 100
    return raw, max(Decimal(0), min(Decimal(100), raw))


def weighted_score(items):
    total = sum((weight for _, weight in items), Decimal(0))
    return sum((value * weight for value, weight in items), Decimal(0)) / total if total else None


def due_after(anchor: date, frequency: str, after: date):
    if frequency in ("weekly", "biweekly"):
        days = 7 if frequency == "weekly" else 14
        steps = max(1, (after - anchor).days // days + 1)
        return anchor + timedelta(days=steps * days)
    months = max(1, (after.year - anchor.year) * 12 + after.month - anchor.month)
    while True:
        year, month0 = divmod(anchor.year * 12 + anchor.month - 1 + months, 12)
        candidate = date(year, month0 + 1, min(anchor.day, calendar.monthrange(year, month0 + 1)[1]))
        if candidate > after:
            return candidate
        months += 1


@dataclass(frozen=True)
class HealthPolicy:
    grace_days: int = 3
    red_confidence: int = 40
    amber_confidence: int = 70
    red_lag: int = 20
    amber_lag: int = 10


def planned_progress(start: date, end: date, today: date):
    duration = max(1, (end - start).days)
    return max(Decimal(0), min(Decimal(100), Decimal((today - start).days) * 100 / Decimal(duration)))


def health(value, planned, confidence, last_update, due, today, severe=False, policy=HealthPolicy()):
    if last_update is None or today > due + timedelta(days=policy.grace_days):
        return "Gray"
    lag = planned - value
    if severe or confidence < policy.red_confidence or lag > policy.red_lag:
        return "Red"
    if confidence < policy.amber_confidence or lag > policy.amber_lag:
        return "Amber"
    return "Green"


def would_cycle(edges, source, target):
    if source == target:
        return True
    graph = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
    pending, seen = [target], set()
    while pending:
        node = pending.pop()
        if node == source:
            return True
        if node not in seen:
            seen.add(node)
            pending.extend(graph.get(node, []))
    return False
