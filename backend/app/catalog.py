"""Rules for shops, services and working hours, kept out of the views so they
can be tested on their own."""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select

from .extensions import db
from .models import Shop, WorkingHours


def slugify(text: str) -> str:
    """'Frizeria Ștefan & Co' -> 'frizeria-stefan-co'"""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60].strip("-")


def slug_taken(slug: str, exclude_shop_id: int | None = None) -> bool:
    query = select(Shop.id).where(Shop.slug == slug)
    if exclude_shop_id is not None:
        query = query.where(Shop.id != exclude_shop_id)
    return db.session.scalar(query) is not None


def unique_slug(name: str) -> str:
    """A free slug based on the shop name: fade-street, then fade-street-2, ..."""
    base = slugify(name) or "shop"
    if len(base) < 3:
        base = f"{base}-shop"
    slug, n = base, 2
    while slug_taken(slug):
        slug = f"{base}-{n}"
        n += 1
    return slug


def to_cents(amount: Decimal | None) -> int:
    if amount is None:
        return 0
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money(cents: int, currency: str) -> str:
    return f"{cents // 100}.{cents % 100:02d} {currency}"


def save_working_hours(member, days: list[list[tuple]]) -> None:
    """Replace a member's weekly hours. days[weekday] is a list of (start, end) times."""
    db.session.execute(delete(WorkingHours).where(WorkingHours.member_id == member.id))
    for weekday, intervals in enumerate(days):
        for start, end in intervals:
            db.session.add(
                WorkingHours(member_id=member.id, weekday=weekday, start_time=start, end_time=end)
            )


def hours_by_day(member) -> list[list[tuple]]:
    days = [[] for _ in range(7)]
    for row in sorted(member.working_hours, key=lambda r: (r.weekday, r.start_time)):
        days[row.weekday].append((row.start_time, row.end_time))
    return days
