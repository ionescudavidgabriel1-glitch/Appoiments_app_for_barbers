import re
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.booking import (
    BOOKING_DAYS_AHEAD,
    SlotTaken,
    available_slots,
    bookable_days,
    busy_times,
    create_booking,
    day_window_utc,
    free_starts,
)
from app.models import (
    Appointment,
    AppointmentStatus,
    Role,
    Service,
    Shop,
    ShopMember,
    TimeOff,
    WorkingHours,
)
from app.timeutils import to_local, utcnow

from .conftest import make_appointment, make_user

# Fade Street is in Europe/Bucharest (UTC+2 in winter). Monday 2 November 2026.
MONDAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 1, 12, 0)  # Sunday noon UTC


def add_hours(db, member, weekday, *shifts):
    for start, end in shifts:
        db.session.add(WorkingHours(member=member, weekday=weekday, start_time=start, end_time=end))
    db.session.commit()


def starts(setup, day=MONDAY, now=NOW, service=None):
    shop, member = setup["shop"], setup["member"]
    service = service or setup["service"]
    window = day_window_utc(shop, day)
    busy = busy_times([member.id], *window, now)[member.id]
    return [t.strftime("%H:%M") for t in free_starts(shop, member, service, day, busy, now)]


def book(setup, start, day=MONDAY, members=None, now=NOW):
    return create_booking(
        setup["shop"],
        setup["service"],
        members or [setup["member"]],
        day,
        start,
        guest_name="Ion Pop",
        guest_email="ion@example.com",
        guest_phone="+40 712 345 678",
        now=now,
    )


# Which times are free


def test_starts_fill_the_shift_on_the_grid(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    # 30 minute service, 15 minute grid: the last start that fits is 11:30.
    assert starts(shop_setup) == [
        "09:00", "09:15", "09:30", "09:45", "10:00", "10:15",
        "10:30", "10:45", "11:00", "11:15", "11:30",
    ]  # fmt: skip


def test_shift_until_midnight_offers_the_last_half_hour(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(23), WorkingHours.END_OF_DAY))
    assert starts(shop_setup) == ["23:00", "23:15", "23:30"]
    appointment, _ = book(shop_setup, time(23, 30))
    # 23:30-00:00 local on Monday is 21:30-22:00 UTC.
    assert (appointment.start_at, appointment.end_at) == (
        datetime(2026, 11, 2, 21, 30),
        datetime(2026, 11, 2, 22, 0),
    )


def test_no_starts_on_a_day_off(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    assert starts(shop_setup, day=MONDAY + timedelta(days=1)) == []


def test_first_start_rounds_up_to_the_grid(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9, 10), time(10)))
    assert starts(shop_setup) == ["09:15", "09:30"]


def test_service_never_runs_into_a_break(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(10)), (time(11), time(12)))
    shop_setup["service"].duration_min = 60
    assert starts(shop_setup) == ["09:00", "11:00"]


def test_existing_appointment_blocks_overlapping_starts(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(11)))
    # 10:00-10:30 local is 08:00-08:30 UTC.
    db.session.add(
        make_appointment(shop_setup, datetime(2026, 11, 2, 8), datetime(2026, 11, 2, 8, 30))
    )
    db.session.commit()
    assert starts(shop_setup) == ["09:00", "09:15", "09:30", "10:30"]


@pytest.mark.parametrize(
    ("overrides", "blocks"),
    [
        ({"status": AppointmentStatus.CANCELLED}, False),
        ({"status": AppointmentStatus.CONFIRMED}, True),
        (
            {
                "status": AppointmentStatus.PENDING_PAYMENT,
                "hold_expires_at": NOW + timedelta(minutes=5),
            },
            True,
        ),
        (
            {
                "status": AppointmentStatus.PENDING_PAYMENT,
                "hold_expires_at": NOW - timedelta(minutes=1),
            },
            False,
        ),
    ],
)
def test_which_appointments_block(db, shop_setup, overrides, blocks):
    add_hours(db, shop_setup["member"], 0, (time(10), time(10, 30)))
    db.session.add(
        make_appointment(
            shop_setup, datetime(2026, 11, 2, 8), datetime(2026, 11, 2, 8, 30), **overrides
        )
    )
    db.session.commit()
    assert starts(shop_setup) == ([] if blocks else ["10:00"])


def test_time_off_blocks(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(11)))
    db.session.add(
        TimeOff(
            member=shop_setup["member"],
            start_at=datetime(2026, 11, 2, 7),  # 09:00 local
            end_at=datetime(2026, 11, 2, 8),  # 10:00 local
        )
    )
    db.session.commit()
    assert starts(shop_setup) == ["10:00", "10:15", "10:30"]


def test_past_times_are_not_offered(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(11)))
    now = datetime(2026, 11, 2, 8, 20)  # 10:20 local
    assert starts(shop_setup, now=now) == ["10:30"]


def test_local_times_follow_daylight_saving(db, shop_setup):
    # Clocks go forward in Bucharest on 29 March 2026, so 09:00 is UTC+3 that day.
    sunday = date(2026, 3, 29)
    add_hours(db, shop_setup["member"], 6, (time(9), time(9, 30)))
    assert starts(shop_setup, day=sunday, now=datetime(2026, 3, 28)) == ["09:00"]
    appointment, _ = book(shop_setup, time(9), day=sunday, now=datetime(2026, 3, 28))
    assert appointment.start_at == datetime(2026, 3, 29, 6, 0)


def test_bookable_days_start_today_in_shop_time(shop_setup):
    late_sunday_utc = datetime(2026, 11, 1, 23, 30)  # already Monday in Bucharest
    days = bookable_days(shop_setup["shop"], late_sunday_utc)
    assert days[0] == MONDAY
    assert len(days) == BOOKING_DAYS_AHEAD


def test_available_slots_lists_every_free_barber(db, shop_setup):
    shop = shop_setup["shop"]
    barber = make_user(db, "radu@example.com", Role.BARBER, name="Radu")
    radu = ShopMember(shop=shop, user=barber, display_name="Radu")
    db.session.add(radu)
    add_hours(db, shop_setup["member"], 0, (time(9), time(9, 30)))
    add_hours(db, radu, 0, (time(9), time(10)))
    slots = available_slots(shop, shop_setup["service"], [shop_setup["member"], radu], MONDAY, NOW)
    assert {t.strftime("%H:%M"): [m.display_name for m in ms] for t, ms in slots.items()} == {
        "09:00": ["Owner", "Radu"],
        "09:15": ["Radu"],
        "09:30": ["Radu"],
    }


# Creating bookings


def test_create_booking_stores_utc_times_and_a_token_hash(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    appointment, token = book(shop_setup, time(10))
    assert (appointment.start_at, appointment.end_at) == (
        datetime(2026, 11, 2, 8),
        datetime(2026, 11, 2, 8, 30),
    )
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert token not in appointment.manage_token_hash
    assert len(appointment.manage_token_hash) == 64


def test_same_time_cannot_be_booked_twice(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    book(shop_setup, time(10))
    with pytest.raises(SlotTaken):
        book(shop_setup, time(10))
    with pytest.raises(SlotTaken):
        book(shop_setup, time(10, 15))  # would overlap 10:00-10:30
    book(shop_setup, time(10, 30))  # right after is fine
    assert len(db.session.scalars(select(Appointment)).all()) == 2


@pytest.mark.parametrize(
    "start",
    [time(8, 45), time(10, 5), time(11, 45)],  # before hours, off the grid, runs past closing
)
def test_times_outside_the_rules_are_rejected(db, shop_setup, start):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    with pytest.raises(SlotTaken):
        book(shop_setup, start)


def test_days_outside_the_booking_window_are_rejected(db, shop_setup):
    far = MONDAY + timedelta(weeks=8)
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    with pytest.raises(SlotTaken):
        book(shop_setup, time(10), day=far)


def test_any_barber_books_the_first_one_free(db, shop_setup):
    shop = shop_setup["shop"]
    barber = make_user(db, "radu@example.com", Role.BARBER, name="Radu")
    radu = ShopMember(shop=shop, user=barber, display_name="Radu")
    db.session.add(radu)
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    add_hours(db, radu, 0, (time(9), time(12)))
    members = [shop_setup["member"], radu]

    first, _ = book(shop_setup, time(10), members=members)
    second, _ = book(shop_setup, time(10), members=members)
    assert (first.member.display_name, second.member.display_name) == ("Owner", "Radu")
    with pytest.raises(SlotTaken):
        book(shop_setup, time(10), members=members)


# Pages


def next_monday():
    """A Monday 1 to 7 days from now in the shop's timezone, always bookable."""
    today = to_local(utcnow(), "Europe/Bucharest").date()
    return today + timedelta(days=7 - today.weekday())


@pytest.fixture
def open_shop(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    return shop_setup


def booking_data(setup, day, start="10:00", **overrides):
    data = {
        "service": str(setup["service"].id),
        "barber": str(setup["member"].id),
        "day": day.isoformat(),
        "start": start,
        "guest_name": "Ion Pop",
        "guest_email": "Ion@Example.com",
        "guest_phone": "+40 712 345 678",
    }
    data.update(overrides)
    return data


def test_booking_page_lists_services(client, open_shop):
    response = client.get("/s/fade-street/")
    assert response.status_code == 200
    assert b"Book at Fade Street" in response.data
    assert b"Haircut" in response.data
    assert b"Choose a barber" not in response.data


def test_unknown_shop_is_404(client, shop_setup):
    assert client.get("/s/nope/").status_code == 404


def test_shop_without_hours_is_not_open_yet(client, shop_setup):
    assert b"isn't open yet" in client.get("/s/fade-street/").data


def test_choosing_service_and_barber_shows_days_and_times(client, open_shop):
    day = next_monday()
    response = client.get(
        "/s/fade-street/",
        query_string={"service": open_shop["service"].id, "barber": "any", "day": day.isoformat()},
    )
    page = response.get_data(as_text=True)
    assert "Pick a day and time" in page
    assert f'value="{day.isoformat()}" data-refresh\n                         checked' in page
    assert 'value="09:00"' in page and 'value="11:30"' in page
    assert "Your details" in page


def test_hidden_service_and_barber_are_not_offered(client, db, open_shop):
    open_shop["service"].active = False
    db.session.add(Service(shop=open_shop["shop"], name="Beard trim", duration_min=20))
    db.session.commit()
    page = client.get("/s/fade-street/").get_data(as_text=True)
    assert "Beard trim" in page and "Haircut" not in page

    open_shop["member"].active = False
    db.session.commit()
    assert "isn't open yet" in client.get("/s/fade-street/").get_data(as_text=True)


def test_guest_books_and_sees_confirmation(client, db, open_shop):
    day = next_monday()
    response = client.post("/s/fade-street/", data=booking_data(open_shop, day))
    assert response.status_code == 302
    location = response.headers["Location"]
    assert re.fullmatch(r"/s/fade-street/booking/[\w-]+\?new=1", location)

    appointment = db.session.scalar(select(Appointment))
    assert appointment.guest_email == "ion@example.com"
    local_start = to_local(appointment.start_at, "Europe/Bucharest").replace(tzinfo=None)
    assert local_start == datetime.combine(day, time(10))

    page = client.get(location).get_data(as_text=True)
    assert "You're booked, Ion." in page
    assert "10:00 to 10:30" in page
    assert 'id="booking-link"' in page
    # Without ?new=1 (opening the saved link later) the link box isn't repeated.
    later = client.get(location.split("?")[0]).get_data(as_text=True)
    assert "Your booking" in later and 'id="booking-link"' not in later


def test_taken_time_sends_guest_back_to_pick_again(client, db, open_shop):
    day = next_monday()
    client.post("/s/fade-street/", data=booking_data(open_shop, day))
    response = client.post("/s/fade-street/", data=booking_data(open_shop, day))
    # 10:00 is no longer offered, so the form treats it as not picked.
    assert response.status_code == 200
    assert b"Pick a service, a barber and a free time first." in response.data
    assert len(db.session.scalars(select(Appointment)).all()) == 1


def test_race_for_the_same_time_shows_taken_message(client, db, open_shop, monkeypatch):
    # Simulate someone else booking between showing the form and saving it.
    import app.blueprints.booking as views

    def taken(*args, **kwargs):
        raise SlotTaken

    monkeypatch.setattr(views, "create_booking", taken)
    response = client.post("/s/fade-street/", data=booking_data(open_shop, next_monday()))
    assert response.status_code == 302
    assert "barber=" in response.headers["Location"]
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "that time was just taken" in page


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"guest_name": ""}, b"Enter your name."),
        ({"guest_email": "nope"}, b"Enter an email like name@example.com."),
        ({"guest_phone": "call me"}, b"Enter a phone number"),
    ],
)
def test_booking_details_are_validated(client, db, open_shop, overrides, message):
    response = client.post(
        "/s/fade-street/", data=booking_data(open_shop, next_monday(), **overrides)
    )
    assert response.status_code == 200
    assert message in response.data
    assert b'value="10:00"' in response.data  # the picked time is kept
    assert db.session.scalars(select(Appointment)).all() == []


def test_time_off_the_grid_is_rejected(client, db, open_shop):
    response = client.post(
        "/s/fade-street/", data=booking_data(open_shop, next_monday(), start="10:05")
    )
    assert b"Pick a service, a barber and a free time first." in response.data
    assert db.session.scalars(select(Appointment)).all() == []


def test_booking_link_only_works_for_its_shop(client, db, open_shop):
    client.post("/s/fade-street/", data=booking_data(open_shop, next_monday()))
    token = db.session.scalar(select(Appointment)).manage_token_hash  # a hash is not a token
    assert client.get(f"/s/fade-street/booking/{token}").status_code == 404

    other_owner = make_user(db, "other@example.com", Role.OWNER)
    db.session.add(Shop(owner=other_owner, name="Other", slug="other"))
    db.session.commit()
    location = client.post(
        "/s/fade-street/", data=booking_data(open_shop, next_monday(), start="11:00")
    )
    real_token = location.headers["Location"].split("/booking/")[1].split("?")[0]
    assert client.get(f"/s/other/booking/{real_token}").status_code == 404
    assert client.get(f"/s/fade-street/booking/{real_token}").status_code == 200
