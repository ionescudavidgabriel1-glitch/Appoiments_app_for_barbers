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
    CannotChange,
    SlotTaken,
    available_slots,
    bookable_members,
    bookable_services,
    can_change,
    cancel_booking,
    create_booking,
    days_with_slots,
    reschedule_booking,
)
from ..extensions import db
from ..forms import BookingDetailsForm
from ..models import Appointment, Shop
from ..notifications import notify_booked, notify_cancelled, notify_moved
from ..security import hash_token
from ..timeutils import to_local, utcnow

bp = Blueprint("booking", __name__)

ANY_BARBER = "any"


def shop_or_404(slug: str) -> Shop:
    shop = db.session.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None:
        abort(404)
    return shop


def read_choices(shop: Shop, values, service=None, members=None, ignore=None) -> dict:
    """Turn ?service=&barber=&day=&start= into objects, dropping anything invalid.

    Each step only counts if the steps before it are valid, so changing the
    service clears a time that no longer fits.

    For rescheduling, `service` fixes the service, `members` limits the barbers
    (a barber only moves their own bookings) and `ignore` is the booking being
    moved, so its current time counts as free.
    """
    now = utcnow()
    services = [service] if service else bookable_services(shop)
    members = bookable_members(shop) if members is None else members
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

    if service:
        choice["service"] = service
    else:
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

    choice["days"] = days_with_slots(shop, choice["service"], choice["candidates"], now, ignore)
    day = parse_date(values.get("day"))
    if day is None or not choice["days"].get(day):
        # Default to the first day with a free time.
        day = next((d for d, free in choice["days"].items() if free), None)
    if day is None:
        return choice
    choice["day"] = day

    choice["slots"] = available_slots(
        shop, choice["service"], choice["candidates"], day, now, ignore
    )
    choice["slot_groups"] = group_by_part_of_day(choice["slots"])
    start = parse_time(values.get("start"))
    if start in choice["slots"]:
        choice["start"] = start
    return choice


def reschedule_defaults(values, appointment: Appointment, shop: Shop, barber: str) -> dict:
    """Start the reschedule page on the booking's own day and barber choice."""
    values = dict(values.items())
    values.setdefault("barber", barber)
    values.setdefault("day", to_local(appointment.start_at, shop.timezone).date().isoformat())
    return values


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

    notify_booked(appointment)
    return redirect(url_for("booking.confirmation", slug=shop.slug, token=token, new=1))


def guest_appointment_or_404(shop: Shop, token: str) -> Appointment:
    """The private link is the only key to a guest's booking."""
    appointment = db.session.scalar(
        select(Appointment).where(
            Appointment.manage_token_hash == hash_token(token), Appointment.shop_id == shop.id
        )
    )
    if appointment is None:
        abort(404)
    return appointment


@bp.get("/<slug>/booking/<token>")
def confirmation(slug, token):
    shop = shop_or_404(slug)
    appointment = guest_appointment_or_404(shop, token)
    start = to_local(appointment.start_at, shop.timezone)
    end = to_local(appointment.end_at, shop.timezone)
    return render_template(
        "booking/confirmation.html",
        shop=shop,
        appointment=appointment,
        token=token,
        start=start,
        end=end,
        is_new=request.args.get("new") == "1",
        link=url_for("booking.confirmation", slug=shop.slug, token=token, _external=True),
        is_past=appointment.start_at < utcnow(),
        can_change=can_change(appointment, utcnow()),
    )


@bp.post("/<slug>/booking/<token>/cancel")
def guest_cancel(slug, token):
    shop = shop_or_404(slug)
    appointment = guest_appointment_or_404(shop, token)
    try:
        cancel_booking(appointment, utcnow())
        notify_cancelled(appointment)
        flash("Your booking is cancelled. The time is free for someone else.", "success")
    except CannotChange:
        flash("This booking can't be cancelled online any more.", "error")
    return redirect(url_for("booking.confirmation", slug=shop.slug, token=token))


@bp.route("/<slug>/booking/<token>/reschedule", methods=["GET", "POST"])
def guest_reschedule(slug, token):
    shop = shop_or_404(slug)
    a = guest_appointment_or_404(shop, token)
    back = url_for("booking.confirmation", slug=shop.slug, token=token)
    if not can_change(a, utcnow()):
        flash("This booking can't be moved online any more.", "error")
        return redirect(back)

    values = request.form if request.method == "POST" else request.args
    values = reschedule_defaults(values, a, shop, str(a.member_id))
    c = read_choices(shop, values, service=a.service, ignore=a)

    if request.method == "POST":
        if c["start"] is None:
            flash("Pick a new time first.", "error")
        else:
            try:
                old_member = a.member
                reschedule_booking(a, c["candidates"], c["day"], c["start"], utcnow())
                notify_moved(a, old_member)
                flash("Your booking has moved. See you then!", "success")
                return redirect(back)
            except (SlotTaken, CannotChange):
                flash("Sorry, that time was just taken. Please pick another one.", "error")
                c = read_choices(shop, values, service=a.service, ignore=a)

    start = to_local(a.start_at, shop.timezone)
    end = to_local(a.end_at, shop.timezone)
    return render_template(
        "booking/reschedule.html",
        shop=shop,
        a=a,
        c=c,
        any=ANY_BARBER,
        start=start,
        end=end,
        form_url=url_for("booking.guest_reschedule", slug=shop.slug, token=token),
        back_url=back,
        public=True,
    )
