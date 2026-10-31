"""The shop's daily calendar, managing single bookings, and barbers' time off.

Owners see and manage every booking at their shop. A barber sees and manages
only their own bookings and time off. Anyone else gets 404.
"""

from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from ..booking import (
    CannotChange,
    SlotTaken,
    bookable_members,
    can_change,
    can_record_outcome,
    cancel_booking,
    day_window_utc,
    record_outcome,
    reschedule_booking,
)
from ..extensions import db
from ..forms import TimeOffForm, shown_end
from ..models import Appointment, AppointmentStatus, Shop, ShopMember, TimeOff
from ..timeutils import to_local, to_utc, utcnow
from .booking import ANY_BARBER, parse_date, read_choices, reschedule_defaults

bp = Blueprint("calendar", __name__)


class Access:
    """Who is looking at a shop: its owner, and/or one of its barbers."""

    def __init__(self, slug: str):
        self.shop = db.session.scalar(select(Shop).where(Shop.slug == slug))
        if self.shop is None:
            abort(404)
        self.is_owner = self.shop.owner_id == current_user.id
        self.member = next((m for m in self.shop.members if m.user_id == current_user.id), None)
        if not self.is_owner and self.member is None:
            abort(404)

    def members(self) -> list[ShopMember]:
        """Barbers whose calendar this person can see."""
        if self.is_owner:
            return sorted(self.shop.members, key=lambda m: (not m.active, m.display_name.lower()))
        return [self.member]

    def can_manage_member(self, member: ShopMember) -> bool:
        return self.is_owner or (self.member is not None and member.id == self.member.id)

    def appointment_or_404(self, appointment_id: int) -> Appointment:
        appointment = db.session.get(Appointment, appointment_id)
        if (
            appointment is None
            or appointment.shop_id != self.shop.id
            or not self.can_manage_member(appointment.member)
        ):
            abort(404)
        return appointment

    def member_or_404(self, member_id: int) -> ShopMember:
        member = db.session.get(ShopMember, member_id)
        if member is None or member.shop_id != self.shop.id or not self.can_manage_member(member):
            abort(404)
        return member


def local_times(appointment: Appointment, tz: str) -> tuple[datetime, datetime]:
    return to_local(appointment.start_at, tz), to_local(appointment.end_at, tz)


# Calendar


@bp.get("/<slug>/calendar")
@login_required
def day_view(slug):
    access = Access(slug)
    shop = access.shop
    today = to_local(utcnow(), shop.timezone).date()
    day = parse_date(request.args.get("day")) or today
    start, end = day_window_utc(shop, day)
    members = access.members()

    appointments = db.session.scalars(
        select(Appointment)
        .where(
            Appointment.shop_id == shop.id,
            Appointment.member_id.in_([m.id for m in members]),
            Appointment.start_at < end,
            Appointment.end_at > start,
        )
        .order_by(Appointment.start_at)
    ).all()
    time_off = db.session.scalars(
        select(TimeOff).where(
            TimeOff.member_id.in_([m.id for m in members]),
            TimeOff.start_at < end,
            TimeOff.end_at > start,
        )
    ).all()

    columns = []
    for member in members:
        shifts = sorted(
            (h for h in member.working_hours if h.weekday == day.weekday()),
            key=lambda h: h.start_time,
        )
        mine = [a for a in appointments if a.member_id == member.id]
        if not member.active and not mine:
            continue
        columns.append(
            {
                "member": member,
                "shifts": [(h.start_time, shown_end(h.end_time)) for h in shifts],
                "time_off": [t for t in time_off if t.member_id == member.id],
                "rows": [(a, *local_times(a, shop.timezone)) for a in mine],
                "booked": sum(1 for a in mine if a.status != AppointmentStatus.CANCELLED),
            }
        )

    return render_template(
        "calendar/day.html",
        shop=shop,
        access=access,
        day=day,
        today=today,
        prev_day=day - timedelta(days=1),
        next_day=day + timedelta(days=1),
        columns=columns,
    )


# One booking


@bp.get("/<slug>/appointments/<int:appointment_id>")
@login_required
def appointment(slug, appointment_id):
    access = Access(slug)
    a = access.appointment_or_404(appointment_id)
    start, end = local_times(a, access.shop.timezone)
    now = utcnow()
    return render_template(
        "calendar/appointment.html",
        shop=access.shop,
        a=a,
        start=start,
        end=end,
        can_change=can_change(a, now),
        can_record_outcome=can_record_outcome(a, now),
    )


def back_to(a: Appointment):
    return redirect(url_for("calendar.appointment", slug=a.shop.slug, appointment_id=a.id))


@bp.post("/<slug>/appointments/<int:appointment_id>/cancel")
@login_required
def cancel(slug, appointment_id):
    a = Access(slug).appointment_or_404(appointment_id)
    try:
        cancel_booking(a, utcnow())
        flash(f"{a.guest_name}'s booking is cancelled. The time is free again.", "success")
    except CannotChange:
        flash("This booking can't be cancelled any more.", "error")
    return back_to(a)


@bp.post("/<slug>/appointments/<int:appointment_id>/completed")
@login_required
def mark_completed(slug, appointment_id):
    return set_outcome(slug, appointment_id, AppointmentStatus.COMPLETED, "Marked as completed.")


@bp.post("/<slug>/appointments/<int:appointment_id>/no-show")
@login_required
def mark_no_show(slug, appointment_id):
    return set_outcome(slug, appointment_id, AppointmentStatus.NO_SHOW, "Marked as a no-show.")


def set_outcome(slug, appointment_id, status, message):
    a = Access(slug).appointment_or_404(appointment_id)
    try:
        record_outcome(a, status, utcnow())
        flash(message, "success")
    except CannotChange:
        flash("You can record how it went once the appointment has started.", "error")
    return back_to(a)


@bp.route("/<slug>/appointments/<int:appointment_id>/reschedule", methods=["GET", "POST"])
@login_required
def reschedule(slug, appointment_id):
    access = Access(slug)
    a = access.appointment_or_404(appointment_id)
    if not can_change(a, utcnow()):
        flash("This booking can't be moved any more.", "error")
        return back_to(a)

    members = bookable_members(access.shop) if access.is_owner else [access.member]
    values = request.form if request.method == "POST" else request.args
    barber = str(a.member_id) if len(members) == 1 else ANY_BARBER
    values = reschedule_defaults(values, a, access.shop, barber)
    c = read_choices(access.shop, values, service=a.service, members=members, ignore=a)

    if request.method == "POST":
        if c["start"] is None:
            flash("Pick a new time first.", "error")
        else:
            try:
                reschedule_booking(a, c["candidates"], c["day"], c["start"], utcnow())
                flash(f"Moved to {format_when(a, access.shop.timezone)}.", "success")
                return back_to(a)
            except (SlotTaken, CannotChange):
                flash("That time was just taken. Please pick another one.", "error")
                c = read_choices(access.shop, values, service=a.service, members=members, ignore=a)

    start, end = local_times(a, access.shop.timezone)
    url = url_for("calendar.reschedule", slug=slug, appointment_id=a.id)
    return render_template(
        "booking/reschedule.html",
        shop=access.shop,
        a=a,
        c=c,
        any=ANY_BARBER,
        start=start,
        end=end,
        form_url=url,
        back_url=url_for("calendar.appointment", slug=slug, appointment_id=a.id),
        public=False,
    )


def format_when(a: Appointment, tz: str) -> str:
    start = to_local(a.start_at, tz)
    return f"{start:%A} {start.day} {start:%B} at {start:%H:%M} with {a.member.display_name}"


# Time off


@bp.route("/<slug>/barbers/<int:member_id>/time-off", methods=["GET", "POST"])
@login_required
def time_off(slug, member_id):
    access = Access(slug)
    shop = access.shop
    member = access.member_or_404(member_id)
    form = TimeOffForm()
    now = utcnow()

    if form.validate_on_submit():
        start = to_utc(form.start.data, shop.timezone)
        end = to_utc(form.end.data, shop.timezone)
        if end <= now:
            form.end.errors.append("Pick a time in the future.")
        else:
            db.session.add(
                TimeOff(member=member, start_at=start, end_at=end, reason=form.reason.data or None)
            )
            db.session.commit()
            flash(f"Time off saved. {member.display_name} can't be booked then.", "success")
            clashes = db.session.scalars(
                select(Appointment).where(
                    Appointment.member_id == member.id,
                    Appointment.status.in_(AppointmentStatus.BLOCKING),
                    Appointment.start_at < end,
                    Appointment.end_at > start,
                )
            ).all()
            if clashes:
                n = len(clashes)
                flash(
                    f"{n} {'booking is' if n == 1 else 'bookings are'} already in that time. "
                    "They stay booked: move or cancel them from the calendar.",
                    "error",
                )
            return redirect(url_for("calendar.time_off", slug=slug, member_id=member.id))

    upcoming = db.session.scalars(
        select(TimeOff)
        .where(TimeOff.member_id == member.id, TimeOff.end_at > now)
        .order_by(TimeOff.start_at)
    ).all()
    return render_template(
        "calendar/time_off.html",
        shop=shop,
        member=member,
        form=form,
        is_owner=access.is_owner,
        upcoming=[
            (t, to_local(t.start_at, shop.timezone), to_local(t.end_at, shop.timezone))
            for t in upcoming
        ],
    )


@bp.post("/<slug>/barbers/<int:member_id>/time-off/<int:time_off_id>/delete")
@login_required
def delete_time_off(slug, member_id, time_off_id):
    member = Access(slug).member_or_404(member_id)
    entry = db.session.get(TimeOff, time_off_id)
    if entry is None or entry.member_id != member.id:
        abort(404)
    db.session.delete(entry)
    db.session.commit()
    flash("Time off removed. Those times can be booked again.", "info")
    return redirect(url_for("calendar.time_off", slug=slug, member_id=member.id))
