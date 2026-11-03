from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import settings


def business_date(instant: datetime):
    utc = instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant
    return utc.astimezone(ZoneInfo(settings().business_timezone)).date()


def today():
    return business_date(datetime.now(timezone.utc))
