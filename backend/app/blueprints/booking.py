"""Public booking pages for guests, served at /s/<shop-slug>.

The booking page is one form. Choosing a service, barber, day or time reloads
the page with those choices in the URL (?service=..&barber=..&day=..&start=..);
HTMX swaps only the steps section, so it feels instant. Without JavaScript a
"Show times" button does the same with a normal page load.
"""

from datetime import date, time

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from ..booking import (
    SlotTaken,
    available_slots,
    bookable_members,
    bookable_services,
    create_booking,
    days_with_slots,
)
from ..extensions import db
from ..forms import BookingDetailsForm
from ..models import Appointment, Shop
from ..security import hash_token
from ..timeutils import to_local, utcnow

bp = Blueprint("booking", __name__)

ANY_BARBER = "any"


def shop_or_404(slug: str) -> Shop:
    shop = db.session.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None:
        abort(404)
    return shop


def read_choices(shop: Shop, values) -> dict:
    """Turn ?service=&barber=&day=&start= into objects, dropping anything invalid.

    Each step only counts if the steps before it are valid, so changing the
    service clears a time that no longer fits.
    """
    now = utcnow()
    services = bookable_services(shop)
    members = bookable_members(shop)
    choice = {
        "services": services,
        "members": members,
        "service": None,
        "barber": None,  # "any" or a ShopMember
        "candidates": [],  # members to try, in order
        "days": {},
        "day": None,
        "slots": {},
        "slot_groups": [],  # [("Morning", [times]), ...], empty parts left out
        "start": None,
    }

    choice["service"] = next((s for s in services if str(s.id) == values.get("service")), None)
    if choice["service"] is None:
        return choice

    barber = values.get("barber")
    if barber == ANY_BARBER and members:
        choice["barber"], choice["candidates"] = ANY_BARBER, members
    else:
        member = next((m for m in members if str(m.id) == barber), None)
        if member is None:
            return choice
        choice["barber"], choice["candidates"] = member, [member]

    choice["days"] = days_with_slots(shop, choice["service"], choice["candidates"], now)
    day = parse_date(values.get("day"))
    if day is None or not choice["days"].get(day):
        # Default to the first day with a free time.
        day = next((d for d, free in choice["days"].items() if free), None)
    if day is None:
        return choice
    choice["day"] = day

    choice["slots"] = available_slots(shop, choice["service"], choice["candidates"], day, now)
    choice["slot_groups"] = group_by_part_of_day(choice["slots"])
    start = parse_time(values.get("start"))
    if start in choice["slots"]:
        choice["start"] = start
    return choice


def group_by_part_of_day(slots) -> list[tuple[str, list[time]]]:
    parts = [("Morning", 0, 12), ("Afternoon", 12, 17), ("Evening", 17, 24)]
    groups = [(label, [t for t in slots if low <= t.hour < high]) for label, low, high in parts]
    return [(label, times) for label, times in groups if times]


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_time(value):
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@bp.get("/<slug>/")
def book(slug):
    shop = shop_or_404(slug)
    choice = read_choices(shop, request.args)
    form = BookingDetailsForm()
    return render_template("booking/book.html", shop=shop, c=choice, form=form, any=ANY_BARBER)


@bp.post("/<slug>/")
def submit(slug):
    shop = shop_or_404(slug)
    choice = read_choices(shop, request.form)
    form = BookingDetailsForm()

    if choice["start"] is None:
        flash("Pick a service, a barber and a free time first.", "error")
        return render_template("booking/book.html", shop=shop, c=choice, form=form, any=ANY_BARBER)
    if not form.validate_on_submit():
        return render_template("booking/book.html", shop=shop, c=choice, form=form, any=ANY_BARBER)

    try:
        appointment, token = create_booking(
            shop,
            choice["service"],
            choice["candidates"],
            choice["day"],
            choice["start"],
            guest_name=form.guest_name.data,
            guest_email=form.guest_email.data.lower(),
            guest_phone=form.guest_phone.data,
            now=utcnow(),
        )
    except SlotTaken:
        flash("Sorry, that time was just taken. Please pick another one.", "error")
        return redirect(
            url_for(
                "booking.book",
                slug=shop.slug,
                service=choice["service"].id,
                barber=request.form.get("barber"),
                day=choice["day"].isoformat(),
            )
        )

    return redirect(url_for("booking.confirmation", slug=shop.slug, token=token, new=1))


@bp.get("/<slug>/booking/<token>")
def confirmation(slug, token):
    """The guest's private page for their booking. The link is the only key."""
    shop = shop_or_404(slug)
    appointment = db.session.scalar(
        select(Appointment).where(
            Appointment.manage_token_hash == hash_token(token), Appointment.shop_id == shop.id
        )
    )
    if appointment is None:
        abort(404)
    start = to_local(appointment.start_at, shop.timezone)
    end = to_local(appointment.end_at, shop.timezone)
    return render_template(
        "booking/confirmation.html",
        shop=shop,
        appointment=appointment,
        start=start,
        end=end,
        is_new=request.args.get("new") == "1",
        link=url_for("booking.confirmation", slug=shop.slug, token=token, _external=True),
        is_past=appointment.start_at < utcnow(),
    )
