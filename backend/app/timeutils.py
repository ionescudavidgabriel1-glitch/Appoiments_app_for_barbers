"""Time helpers.

All datetimes are stored in the database as naive UTC. Convert to the shop's
timezone only when showing times to people or reading times they enter.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def to_local(dt_utc: datetime, tz_name: str) -> datetime:
    return dt_utc.replace(tzinfo=UTC).astimezone(ZoneInfo(tz_name))


def to_utc(dt_local: datetime, tz_name: str) -> datetime:
    """Convert a naive local time in tz_name to naive UTC."""
    aware = dt_local.replace(tzinfo=ZoneInfo(tz_name))
    return aware.astimezone(UTC).replace(tzinfo=None)
