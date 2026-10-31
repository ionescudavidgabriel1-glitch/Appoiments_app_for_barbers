"""Booking rules: which start times are free, and creating a booking safely.

Plain Python on purpose (no scheduling library), so every rule is visible and
tested. All database times are naive UTC. Customers pick times in the shop's
local time, so this module converts between the two with the shop's timezone.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import (
    Appointment,
    AppointmentStatus,
    Service,
    Shop,
    ShopMember,
    TimeOff,
    WorkingHours,
)
from .security import hash_token, new_booking_token
from .timeutils import to_local, to_utc

BOOKING_DAYS_AHEAD = 30


class SlotTaken(Exception):
    """The chosen time is no longer free (someone else booked it, or it passed)."""


@dataclass(frozen=True)
class Busy:
    start: datetime  # UTC
    end: datetime  # UTC


def bookable_members(shop: Shop) -> list[ShopMember]:
    """Barbers customers can pick: active and with at least one working-hours row."""
    members = [m for m in shop.members if m.active and m.working_hours]
    return sorted(members, key=lambda m: m.display_name.lower())


def bookable_services(shop: Shop) -> list[Service]:
    return sorted((s for s in shop.services if s.active), key=lambda s: s.name.lower())


def bookable_days(shop: Shop, now: datetime) -> list[date]:
    """Today and the next days customers can book, in the shop's local calendar."""
    today = to_local(now, shop.timezone).date()
    return [today + timedelta(days=n) for n in range(BOOKING_DAYS_AHEAD)]


def busy_times(
    member_ids: list[int],
    start: datetime,
    end: datetime,
    now: datetime,
    ignore: Appointment | None = None,
):
    """Appointments and time off that block each member between start and end (UTC).

    `ignore` leaves one appointment out, so a booking being moved doesn't block
    its own current time.
    """
    busy = {member_id: [] for member_id in member_ids}
    if not member_ids:
        return busy

    query = select(Appointment).where(
        Appointment.member_id.in_(member_ids),
        Appointment.status.in_(AppointmentStatus.BLOCKING),
        # An unpaid deposit booking stops blocking once its hold expires.
        or_(Appointment.hold_expires_at.is_(None), Appointment.hold_expires_at > now),
        Appointment.start_at < end,
        Appointment.end_at > start,
    )
    if ignore is not None:
        query = query.where(Appointment.id != ignore.id)
    for a in db.session.scalars(query):
        busy[a.member_id].append(Busy(a.start_at, a.end_at))

    time_off = db.session.scalars(
        select(TimeOff).where(
            TimeOff.member_id.in_(member_ids), TimeOff.start_at < end, TimeOff.end_at > start
        )
    )
    for t in time_off:
        busy[t.member_id].append(Busy(t.start_at, t.end_at))
    return busy


def free_starts(
    shop: Shop, member: ShopMember, service: Service, day: date, busy: list[Busy], now: datetime
) -> list[time]:
    """Local start times on `day` when `member` can do `service`.

    A start is offered when it lies on the shop's grid (every slot_minutes from
    midnight), the whole service fits inside one working shift, it is in the
    future, and it doesn't overlap anything in `busy`.
    """
    grid = shop.slot_minutes
    length = timedelta(minutes=service.duration_min)
    midnight = datetime.combine(day, time())
    starts = []

    for shift in member.working_hours:
        if shift.weekday != day.weekday():
            continue
        shift_start = datetime.combine(day, shift.start_time)
        if shift.end_time == WorkingHours.END_OF_DAY:
            shift_end = datetime.combine(day + timedelta(days=1), time())
        else:
            shift_end = datetime.combine(day, shift.end_time)
        minutes = shift_start.hour * 60 + shift_start.minute
        candidate = midnight + timedelta(minutes=-(-minutes // grid) * grid)  # round up to grid

        while candidate + length <= shift_end:
            start_utc = to_utc(candidate, shop.timezone)
            end_utc = start_utc + length
            if start_utc > now and not any(b.start < end_utc and b.end > start_utc for b in busy):
                starts.append(candidate.time())
            candidate += timedelta(minutes=grid)

    return sorted(set(starts))


def day_window_utc(shop: Shop, day: date) -> tuple[datetime, datetime]:
    start = to_utc(datetime.combine(day, time()), shop.timezone)
    end = to_utc(datetime.combine(day + timedelta(days=1), time()), shop.timezone)
    return start, end


def available_slots(
    shop: Shop,
    service: Service,
    members: list[ShopMember],
    day: date,
    now: datetime,
    ignore: Appointment | None = None,
) -> dict[time, list[ShopMember]]:
    """Free local start times on `day`, each with the members free at that time."""
    start, end = day_window_utc(shop, day)
    busy = busy_times([m.id for m in members], start, end, now, ignore)
    slots: dict[time, list[ShopMember]] = {}
    for member in members:
        for t in free_starts(shop, member, service, day, busy[member.id], now):
            slots.setdefault(t, []).append(member)
    return dict(sorted(slots.items()))


def days_with_slots(
    shop: Shop,
    service: Service,
    members: list[ShopMember],
    now: datetime,
    ignore: Appointment | None = None,
) -> dict[date, bool]:
    """For each bookable day, whether at least one time is free."""
    days = bookable_days(shop, now)
    start, _ = day_window_utc(shop, days[0])
    _, end = day_window_utc(shop, days[-1])
    busy = busy_times([m.id for m in members], start, end, now, ignore)
    return {
        day: any(free_starts(shop, m, service, day, busy[m.id], now) for m in members)
        for day in days
    }


def _place(shop, service, members, day, start, now, save, ignore=None):
    """Try each member in order: if they are free at `start`, call save(member, start_utc)
    and commit. Returns save's result, or raises SlotTaken.

    The availability check runs here, inside the transaction, with the member's
    row locked (on PostgreSQL), so two people can't take overlapping times. The
    unique index on (member, start) is the last line of defense.
    """
    if day not in bookable_days(shop, now):
        raise SlotTaken
    window_start, window_end = day_window_utc(shop, day)

    for member in members:
        db.session.execute(
            select(ShopMember.id).where(ShopMember.id == member.id).with_for_update()
        )
        busy = busy_times([member.id], window_start, window_end, now, ignore)[member.id]
        if start not in free_starts(shop, member, service, day, busy, now):
            continue
        result = save(member, to_utc(datetime.combine(day, start), shop.timezone))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            continue
        return result

    db.session.rollback()
    raise SlotTaken


def create_booking(
    shop: Shop,
    service: Service,
    members: list[ShopMember],
    day: date,
    start: time,
    guest_name: str,
    guest_email: str,
    guest_phone: str,
    now: datetime,
) -> tuple[Appointment, str]:
    """Book the first of `members` who is free at `start` on `day`.

    Returns the appointment and the raw manage-link token (only its hash is
    stored). Raises SlotTaken if nobody is free any more.
    """
    nonce, token = new_booking_token()

    def save(member, start_utc):
        appointment = Appointment(
            shop=shop,
            member=member,
            service=service,
            start_at=start_utc,
            end_at=start_utc + timedelta(minutes=service.duration_min),
            guest_name=guest_name,
            guest_email=guest_email,
            guest_phone=guest_phone,
            status=AppointmentStatus.CONFIRMED,
            manage_token_hash=hash_token(token),
            manage_nonce=nonce,
        )
        db.session.add(appointment)
        return appointment, token

    return _place(shop, service, members, day, start, now, save)


# Changing bookings (phase 5)


class CannotChange(Exception):
    """The booking can't be changed this way any more (already started, cancelled...)."""


def can_change(appointment: Appointment, now: datetime) -> bool:
    """Cancel and reschedule are allowed until the appointment starts."""
    return appointment.status in AppointmentStatus.BLOCKING and appointment.start_at > now


def can_record_outcome(appointment: Appointment, now: datetime) -> bool:
    """Completed / no-show can be set once the appointment has started, and corrected later."""
    return appointment.start_at <= now and appointment.status in (
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.NO_SHOW,
    )


def reschedule_booking(
    appointment: Appointment, members: list[ShopMember], day: date, start: time, now: datetime
) -> Appointment:
    """Move a booking to `start` on `day` with the first free of `members`.
    The service stays the same. Raises CannotChange or SlotTaken."""
    if not can_change(appointment, now):
        raise CannotChange
    service = appointment.service

    def save(member, start_utc):
        appointment.member = member
        appointment.start_at = start_utc
        appointment.end_at = start_utc + timedelta(minutes=service.duration_min)
        appointment.reminder_24h_sent_at = None
        appointment.reminder_2h_sent_at = None
        return appointment

    return _place(appointment.shop, service, members, day, start, now, save, ignore=appointment)


def cancel_booking(appointment: Appointment, now: datetime) -> None:
    if not can_change(appointment, now):
        raise CannotChange
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = now
    db.session.commit()


def record_outcome(appointment: Appointment, status: str, now: datetime) -> None:
    if status not in (AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW):
        raise ValueError(status)
    if not can_record_outcome(appointment, now):
        raise CannotChange
    appointment.status = status
    db.session.commit()
