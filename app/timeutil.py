"""Timezone strategy for the POS database.

Stored instants are timezone-aware UTC (PostgreSQL timestamptz).
Pakistan Standard Time is Asia/Karachi, UTC+5, with no daylight saving.
Build local restaurant times in Asia/Karachi, then let PostgreSQL store them.
Display code should convert timestamptz values back to Asia/Karachi.
"""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

PAKISTAN = ZoneInfo("Asia/Karachi")


def utcnow():
    return datetime.now(timezone.utc)


def pakistan_local(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=PAKISTAN)


def as_pakistan(value):
    if value.tzinfo is None:
        raise ValueError("Expected a timezone-aware timestamp")
    return value.astimezone(PAKISTAN)


def parse_hhmm(text):
    hour, minute = text.split(":")
    return time(int(hour), int(minute))
