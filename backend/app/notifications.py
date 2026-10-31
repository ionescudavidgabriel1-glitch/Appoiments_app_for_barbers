"""Emails to guests and barbers about bookings, and appointment reminders.

Who gets what:
- The guest: confirmation, moved, cancelled, and reminders 24 hours and 2 hours
  before the appointment.
- The barber: new booking, moved and cancelled, unless the barber made that
  change themselves. The owner gets no emails.

Every email is written in the shop's language (Shop.language). Sending never
raises: a failed email is logged, and the booking change it is about still stands.
"""

import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from babel.dates import format_date
from flask import current_app, render_template, url_for
from flask_babel import force_locale
from flask_babel import gettext as _
from sqlalchemy import select, update

from .catalog import format_money
from .extensions import db
from .models import Appointment, AppointmentStatus, ShopMember
from .security import booking_token
from .timeutils import to_local

log = logging.getLogger(__name__)

REMINDERS = [
    # (name, how long before the start, column that records it was sent)
    ("24h", timedelta(hours=24), Appointment.reminder_24h_sent_at),
    ("2h", timedelta(hours=2), Appointment.reminder_2h_sent_at),
]


# Sending


def send_email(to: str, subject: str, text: str, html: str) -> bool:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = to
    message["Message-ID"] = make_msgid()
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    backend = current_app.config["MAIL_BACKEND"]
    try:
        if backend == "smtp":
            send_smtp(message)
        elif backend == "file":
            save_to_outbox(message)
        elif backend == "console":
            print(f"--- Email to {to}: {subject}\n{text}\n---")
        elif backend == "memory":
            current_app.extensions.setdefault("outbox", []).append(message)
        else:
            raise ValueError(f"Unknown MAIL_BACKEND {backend!r}")
        return True
    except Exception:
        log.exception("Could not send email %r to %s", subject, to)
        return False


def send_smtp(message: EmailMessage) -> None:
    config = current_app.config
    with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=15) as smtp:
        if config["SMTP_USE_TLS"]:
            smtp.starttls()
        if config["SMTP_USERNAME"]:
            smtp.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
        smtp.send_message(message)


def save_to_outbox(message: EmailMessage) -> None:
    """Development: save the email so it can be opened in a mail app or browser."""
    outbox = Path(current_app.instance_path) / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = outbox / f"{stamp}.eml"
    path.write_bytes(bytes(message))
    log.info("Email to %s saved to %s", message["To"], path)


# Building emails


def guest_link(appointment: Appointment) -> str | None:
    """The guest's private booking link, rebuilt from the booking's nonce."""
    if not appointment.manage_nonce:
        return None
    token = booking_token(appointment.manage_nonce)
    return url_for("booking.confirmation", slug=appointment.shop.slug, token=token, _external=True)


def calendar_link(appointment: Appointment) -> str:
    return url_for(
        "calendar.appointment",
        slug=appointment.shop.slug,
        appointment_id=appointment.id,
        _external=True,
    )


def details(appointment: Appointment) -> dict:
    """Date, time and other facts about a booking, in the shop's language."""
    shop = appointment.shop
    start = to_local(appointment.start_at, shop.timezone)
    end = to_local(appointment.end_at, shop.timezone)
    return {
        "date": format_date(start.date(), "EEEE d MMMM", locale=shop.language),
        "time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
        "service": appointment.service.name,
        "price": format_money(appointment.service.price_cents, shop.currency),
        "barber": appointment.member.display_name,
        "guest": appointment.guest_name,
        "shop": shop.name,
    }


def send(appointment: Appointment, to: str, subject: str, **content) -> bool:
    """Render the shared email layout and send it.

    content: heading, intro, button_label, button_url, note, for_barber.
    """
    context = {"a": appointment, "shop": appointment.shop, "d": details(appointment), **content}
    text = render_template("email/booking.txt", **context)
    html = render_template("email/booking.html", **context)
    return send_email(to, subject, text, html)


# What happened -> who hears about it


def notify_booked(appointment: Appointment) -> None:
    with force_locale(appointment.shop.language):
        d = details(appointment)
        send(
            appointment,
            appointment.guest_email,
            _("Booked: %(service)s on %(date)s at %(time)s", **d),
            heading=_("You're booked, %(name)s.", name=first_name(appointment.guest_name)),
            intro=_("See you at %(shop)s.", **d),
            button_label=_("See or change your booking"),
            button_url=guest_link(appointment),
            note=_("Need to change or cancel? Use the button any time before your appointment."),
        )
        barber_email(
            appointment,
            appointment.member,
            _("New booking: %(guest)s on %(date)s at %(time)s", **d),
            heading=_("New booking"),
            intro=_("%(guest)s booked %(service)s with you.", **d),
        )


def notify_moved(
    appointment: Appointment, old_member: ShopMember, by_user_id: int | None = None
) -> None:
    with force_locale(appointment.shop.language):
        d = details(appointment)
        send(
            appointment,
            appointment.guest_email,
            _("Your booking moved: %(date)s at %(time)s", **d),
            heading=_("Your booking has moved"),
            intro=_("Here are the new details of your booking at %(shop)s.", **d),
            button_label=_("See or change your booking"),
            button_url=guest_link(appointment),
        )
        barber_email(
            appointment,
            appointment.member,
            _("Booking moved: %(guest)s, now %(date)s at %(time)s", **d),
            by_user_id=by_user_id,
            heading=_("A booking has moved"),
            intro=_("New details for %(guest)s's booking.", **d),
        )
        if old_member.id != appointment.member_id:
            barber_email(
                appointment,
                old_member,
                _("Moved to %(barber)s: %(guest)s", **d),
                by_user_id=by_user_id,
                heading=_("A booking moved to %(barber)s", **d),
                intro=_("%(guest)s's booking is no longer in your calendar.", **d),
                button_label=None,
            )


def notify_cancelled(appointment: Appointment, by_user_id: int | None = None) -> None:
    with force_locale(appointment.shop.language):
        d = details(appointment)
        send(
            appointment,
            appointment.guest_email,
            _("Cancelled: %(service)s on %(date)s at %(time)s", **d),
            heading=_("Your booking is cancelled"),
            intro=_("This booking at %(shop)s is cancelled.", **d),
            button_label=_("Book another time"),
            button_url=url_for("booking.book", slug=appointment.shop.slug, _external=True),
        )
        barber_email(
            appointment,
            appointment.member,
            _("Cancelled: %(guest)s on %(date)s at %(time)s", **d),
            by_user_id=by_user_id,
            heading=_("A booking is cancelled"),
            intro=_("%(guest)s's booking is cancelled. The time is free again.", **d),
        )


def barber_email(appointment, member, subject, by_user_id=None, button_label="", **content) -> None:
    """Email a barber, unless they made the change themselves."""
    if by_user_id is not None and member.user_id == by_user_id:
        return
    if button_label == "":
        button_label = _("Open in calendar")
    send(
        appointment,
        member.user.email,
        subject,
        for_barber=True,
        button_label=button_label,
        button_url=calendar_link(appointment) if button_label else None,
        **content,
    )


def first_name(name: str) -> str:
    return name.split()[0] if name.split() else name


# Reminders


def send_due_reminders(now: datetime) -> int:
    """Send every reminder that is due. Returns how many were sent.

    A reminder is due when the appointment is confirmed, starts within its
    window (24 hours or 2 hours), and was booked before that window began, so a
    guest who books at 15:00 for 16:00 doesn't get a "see you in 2 hours" email
    right after their confirmation. The 24-hour reminder is skipped once the
    2-hour one is due.

    Each reminder is claimed with a conditional UPDATE before sending, so two
    workers running at once never send the same reminder twice.
    """
    sent = 0
    for name, before, column in REMINDERS:
        query = select(Appointment.id, Appointment.start_at, Appointment.created_at).where(
            Appointment.status == AppointmentStatus.CONFIRMED,
            column.is_(None),
            Appointment.start_at > now,
            Appointment.start_at <= now + before,
        )
        if name == "24h":
            query = query.where(Appointment.start_at > now + timedelta(hours=2))
        # "Booked before the window began" is checked in Python: date arithmetic
        # between two columns doesn't work the same in SQLite and PostgreSQL.
        due = [
            row.id for row in db.session.execute(query) if row.created_at <= row.start_at - before
        ]

        for appointment_id in due:
            claimed = db.session.execute(
                update(Appointment)
                .where(Appointment.id == appointment_id, column.is_(None))
                .values({column.key: now})
            ).rowcount
            db.session.commit()
            if claimed:
                appointment = db.session.get(Appointment, appointment_id)
                send_reminder(appointment, name)
                sent += 1
    return sent


def send_reminder(appointment: Appointment, name: str) -> None:
    with force_locale(appointment.shop.language):
        d = details(appointment)
        if name == "24h":
            subject = _("Reminder: %(service)s on %(date)s at %(time)s", **d)
        else:
            subject = _("Soon: %(service)s at %(time)s", **d)
        send(
            appointment,
            appointment.guest_email,
            subject,
            heading=_("See you soon, %(name)s", name=first_name(appointment.guest_name)),
            intro=_("A reminder of your booking at %(shop)s.", **d),
            button_label=_("See or change your booking"),
            button_url=guest_link(appointment),
            note=_("Can't make it? Please cancel with the button, so someone else can come."),
        )
