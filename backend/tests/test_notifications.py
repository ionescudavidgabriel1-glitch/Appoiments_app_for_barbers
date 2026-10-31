import re
from datetime import time, timedelta

import pytest
from sqlalchemy import select

from app.models import Appointment, AppointmentStatus, Language, Role, Shop, ShopMember
from app.notifications import send_due_reminders
from app.security import booking_token, hash_token, new_booking_token
from app.timeutils import utcnow

from .conftest import login, make_appointment, make_user
from .test_booking import add_hours, booking_data, next_monday

SHOP_FORM = {"currency": "RON", "slot_minutes": "15"}


@pytest.fixture
def outbox(app):
    box = app.extensions.setdefault("outbox", [])
    box.clear()
    return box


@pytest.fixture
def open_shop(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    return shop_setup


def by_recipient(outbox):
    return {m["To"]: m for m in outbox}


def text_of(message):
    return message.get_body(("plain",)).get_content()


def html_of(message):
    return message.get_body(("html",)).get_content()


def book(client, setup, start="10:00", **overrides):
    data = booking_data(setup, next_monday(), start=start, **overrides)
    return client.post("/s/fade-street/", data=data).headers["Location"].split("?")[0]


# Booking, moving, cancelling


def test_booking_emails_the_guest_and_the_barber(client, open_shop, outbox):
    link = book(client, open_shop)
    mails = by_recipient(outbox)
    assert set(mails) == {"ion@example.com", "owner@example.com"}

    guest = mails["ion@example.com"]
    assert guest["Subject"].startswith("Booked: Haircut on Monday")
    assert "You're booked, Ion." in text_of(guest)
    assert "See or change your booking" in html_of(guest)

    barber = mails["owner@example.com"]
    assert barber["Subject"].startswith("New booking: Ion Pop")
    assert "+40 712 345 678" in text_of(barber)  # the barber sees the phone number
    assert "/shops/fade-street/appointments/" in text_of(barber)

    # The link in the guest's email opens their booking.
    emailed = re.search(r"http://localhost(/s/fade-street/booking/\S+)", text_of(guest)).group(1)
    assert emailed == link
    assert client.get(emailed).status_code == 200


def test_emails_use_the_shops_language(client, db, open_shop, outbox):
    open_shop["shop"].language = Language.ROMANIAN
    db.session.commit()
    book(client, open_shop)
    guest = by_recipient(outbox)["ion@example.com"]
    assert guest["Subject"].startswith("Programare confirmată: Haircut, luni")
    assert "Programarea ta e confirmată, Ion." in text_of(guest)
    assert "Frizer: Owner" in text_of(guest)
    assert 'lang="ro"' in html_of(guest)


def test_guest_cancel_emails_guest_and_barber(client, open_shop, outbox):
    link = book(client, open_shop)
    outbox.clear()
    client.post(f"{link}/cancel")
    mails = by_recipient(outbox)
    assert mails["ion@example.com"]["Subject"].startswith("Cancelled: Haircut")
    assert "Book another time" in text_of(mails["ion@example.com"])
    assert mails["owner@example.com"]["Subject"].startswith("Cancelled: Ion Pop")


def test_guest_move_emails_new_details(client, open_shop, outbox):
    link = book(client, open_shop)
    outbox.clear()
    day = next_monday().isoformat()
    member = str(open_shop["member"].id)
    client.post(f"{link}/reschedule", data={"barber": member, "day": day, "start": "11:00"})
    mails = by_recipient(outbox)
    assert "at 11:00" in mails["ion@example.com"]["Subject"]
    assert mails["owner@example.com"]["Subject"].startswith("Booking moved: Ion Pop")


def test_barber_is_not_emailed_about_their_own_change(client, db, open_shop, outbox):
    book(client, open_shop)
    appointment = db.session.scalar(select(Appointment))
    outbox.clear()
    login(client)  # the owner is also this booking's barber
    client.post(f"/shops/fade-street/appointments/{appointment.id}/cancel")
    assert list(by_recipient(outbox)) == ["ion@example.com"]


def test_moving_to_another_barber_tells_the_old_one(client, db, open_shop, outbox):
    radu_user = make_user(db, "radu@example.com", Role.BARBER, name="Radu")
    radu = ShopMember(shop=open_shop["shop"], user=radu_user, display_name="Radu")
    db.session.add(radu)
    add_hours(db, radu, 0, (time(9), time(12)))
    book(client, open_shop, barber=str(radu.id))
    appointment = db.session.scalar(select(Appointment))
    outbox.clear()

    login(client)  # the owner moves Radu's booking to themselves
    client.post(
        f"/shops/fade-street/appointments/{appointment.id}/reschedule",
        data={
            "barber": str(open_shop["member"].id),
            "day": next_monday().isoformat(),
            "start": "11:00",
        },
    )
    mails = by_recipient(outbox)
    # Guest hears the new time, Radu hears it left his calendar, the owner made it so no email.
    assert set(mails) == {"ion@example.com", "radu@example.com"}
    assert mails["radu@example.com"]["Subject"] == "Moved to Owner: Ion Pop"


def test_failed_email_does_not_break_the_booking(app, client, db, open_shop, outbox, caplog):
    app.config["MAIL_BACKEND"] = "smtp"
    app.config["SMTP_HOST"] = "127.0.0.1"
    app.config["SMTP_PORT"] = 1  # nothing listens here
    response = client.post("/s/fade-street/", data=booking_data(open_shop, next_monday()))
    assert response.status_code == 302
    assert db.session.scalar(select(Appointment)).status == AppointmentStatus.CONFIRMED
    assert "Could not send email" in caplog.text


def test_file_backend_saves_eml(app, client, open_shop, tmp_path):
    app.config["MAIL_BACKEND"] = "file"
    app.instance_path = str(tmp_path)
    book(client, open_shop)
    files = list((tmp_path / "outbox").glob("*.eml"))
    assert len(files) == 2
    assert b"Subject: Booked: Haircut" in b"".join(f.read_bytes() for f in files)


# Reminders


def appointment_in(db, setup, hours_from_now, booked_hours_ago=48, **overrides):
    start = utcnow().replace(microsecond=0) + timedelta(hours=hours_from_now)
    nonce, token = new_booking_token()
    a = make_appointment(
        setup,
        start,
        start + timedelta(minutes=30),
        manage_nonce=nonce,
        manage_token_hash=hash_token(token),
        created_at=utcnow() - timedelta(hours=booked_hours_ago),
        **overrides,
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def remind(app):
    def run(now=None):
        with app.test_request_context(base_url=app.config["APP_BASE_URL"]):
            return send_due_reminders(now or utcnow())

    return run


def test_24h_reminder_is_sent_once(db, shop_setup, outbox, remind):
    a = appointment_in(db, shop_setup, hours_from_now=20)
    assert remind() == 1
    assert remind() == 0
    assert outbox[0]["To"] == "guest@example.com"
    assert outbox[0]["Subject"].startswith("Reminder: Haircut on")
    assert "http://127.0.0.1:5000/s/fade-street/booking/" in text_of(outbox[0])
    assert a.reminder_24h_sent_at is not None


def test_2h_reminder_replaces_a_late_24h_one(db, shop_setup, outbox, remind):
    appointment_in(db, shop_setup, hours_from_now=1.5)
    assert remind() == 1
    assert outbox[0]["Subject"].startswith("Soon: Haircut at")


def test_both_reminders_over_time(db, shop_setup, outbox, remind):
    a = appointment_in(db, shop_setup, hours_from_now=23)
    remind()
    remind(now=a.start_at - timedelta(hours=1))
    assert [m["Subject"].split(":")[0] for m in outbox] == ["Reminder", "Soon"]


@pytest.mark.parametrize(
    ("hours_from_now", "booked_hours_ago", "status"),
    [
        (30, 48, AppointmentStatus.CONFIRMED),  # not within 24 hours yet
        (1, 0.5, AppointmentStatus.CONFIRMED),  # booked 30 minutes ago for in 1 hour
        (20, 48, AppointmentStatus.CANCELLED),
        (-1, 48, AppointmentStatus.CONFIRMED),  # already started
    ],
)
def test_no_reminder(db, shop_setup, outbox, remind, hours_from_now, booked_hours_ago, status):
    appointment_in(db, shop_setup, hours_from_now, booked_hours_ago, status=status)
    assert remind() == 0
    assert outbox == []


def test_moving_a_booking_sends_its_reminders_again(client, db, open_shop, outbox, remind):
    a = appointment_in(db, open_shop, hours_from_now=20)
    remind()
    from app.booking import reschedule_booking

    day = next_monday()
    reschedule_booking(a, [open_shop["member"]], day, time(11), utcnow())
    assert a.reminder_24h_sent_at is None and a.reminder_2h_sent_at is None


def test_reminders_in_romanian(db, shop_setup, outbox, remind):
    shop_setup["shop"].language = Language.ROMANIAN
    appointment_in(db, shop_setup, hours_from_now=20)
    remind()
    assert outbox[0]["Subject"].startswith("Reamintire: Haircut,")


def test_send_reminders_command(app, db, shop_setup, outbox):
    appointment_in(db, shop_setup, hours_from_now=20)
    result = app.test_cli_runner().invoke(args=["send-reminders"])
    assert result.output.strip() == "Sent 1 reminder."


# Booking links and shop language


def test_booking_token_is_rebuilt_from_its_nonce(app):
    nonce, token = new_booking_token()
    assert booking_token(nonce) == token
    app.config["SECRET_KEY"] = "another key"
    assert booking_token(nonce) != token


@pytest.mark.parametrize(
    ("timezone", "choice", "language"),
    [
        ("Europe/Bucharest", "auto", "ro"),
        ("Europe/Chisinau", "auto", "ro"),
        ("Europe/London", "auto", "en"),
        ("Europe/Bucharest", "en", "en"),
        ("Europe/London", "ro", "ro"),
    ],
)
def test_shop_language(client, db, timezone, choice, language):
    make_user(db, "new@example.com", Role.OWNER)
    login(client, "new@example.com")
    client.post(
        "/shops/new",
        data={"name": "New Shop", "timezone": timezone, "language": choice, **SHOP_FORM},
    )
    assert db.session.scalar(select(Shop)).language == language


def test_settings_page_shows_the_language(client, db, shop_setup):
    shop_setup["shop"].language = Language.ROMANIAN
    db.session.commit()
    login(client)
    page = client.get("/shops/fade-street/settings").get_data(as_text=True)
    assert "Language of emails" in page
    assert '<option selected value="ro">' in page
