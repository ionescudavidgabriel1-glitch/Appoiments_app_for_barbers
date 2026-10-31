import re
from datetime import time, timedelta

import pytest
from sqlalchemy import select

from app.booking import (
    CannotChange,
    SlotTaken,
    can_change,
    cancel_booking,
    record_outcome,
    reschedule_booking,
)
from app.models import Appointment, AppointmentStatus, Role, ShopMember, TimeOff
from app.timeutils import to_local, utcnow

from .conftest import login, make_appointment, make_user
from .test_booking import MONDAY, NOW, add_hours, book, booking_data, next_monday, starts

# Rules


@pytest.fixture
def monday_booking(db, shop_setup):
    """Owner works Monday 09:00-12:00 and has a 10:00-10:30 booking."""
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    appointment, _ = book(shop_setup, time(10))
    return appointment


def test_can_change_until_it_starts(monday_booking):
    assert can_change(monday_booking, NOW)
    assert not can_change(monday_booking, monday_booking.start_at)
    monday_booking.status = AppointmentStatus.CANCELLED
    assert not can_change(monday_booking, NOW)


def test_cancel_frees_the_time(shop_setup, monday_booking):
    assert "10:00" not in starts(shop_setup)
    cancel_booking(monday_booking, NOW)
    assert monday_booking.status == AppointmentStatus.CANCELLED
    assert monday_booking.cancelled_at == NOW
    assert "10:00" in starts(shop_setup)
    with pytest.raises(CannotChange):
        cancel_booking(monday_booking, NOW)


def test_cannot_cancel_after_it_starts(monday_booking):
    with pytest.raises(CannotChange):
        cancel_booking(monday_booking, monday_booking.start_at + timedelta(minutes=1))


def test_reschedule_can_overlap_its_own_old_time(shop_setup, monday_booking):
    assert "09:45" not in starts(shop_setup)  # 09:45-10:15 overlaps the 10:00 booking
    reschedule_booking(monday_booking, [shop_setup["member"]], MONDAY, time(10, 15), NOW)
    local = to_local(monday_booking.start_at, "Europe/Bucharest")
    assert (local.hour, local.minute) == (10, 15)
    assert monday_booking.end_at - monday_booking.start_at == timedelta(minutes=30)
    # The old 10:00-10:30 no longer blocks, so 09:45-10:15 fits right before the new time.
    assert "09:45" in starts(shop_setup)


def test_reschedule_into_a_taken_time_changes_nothing(db, shop_setup, monday_booking):
    other, _ = book(shop_setup, time(11))
    before = (monday_booking.start_at, monday_booking.member_id)
    with pytest.raises(SlotTaken):
        reschedule_booking(monday_booking, [shop_setup["member"]], MONDAY, time(11), NOW)
    db.session.refresh(monday_booking)
    assert (monday_booking.start_at, monday_booking.member_id) == before


def test_reschedule_to_another_barber(db, shop_setup, monday_booking):
    radu = ShopMember(
        shop=shop_setup["shop"],
        user=make_user(db, "radu@example.com", Role.BARBER),
        display_name="Radu",
    )
    db.session.add(radu)
    add_hours(db, radu, 0, (time(9), time(12)))
    reschedule_booking(monday_booking, [radu], MONDAY, time(10), NOW)
    assert monday_booking.member.display_name == "Radu"


def test_record_outcome_only_after_start(monday_booking):
    with pytest.raises(CannotChange):
        record_outcome(monday_booking, AppointmentStatus.COMPLETED, NOW)
    after = monday_booking.start_at + timedelta(minutes=5)
    record_outcome(monday_booking, AppointmentStatus.COMPLETED, after)
    assert monday_booking.status == AppointmentStatus.COMPLETED
    record_outcome(monday_booking, AppointmentStatus.NO_SHOW, after)  # corrections allowed
    assert monday_booking.status == AppointmentStatus.NO_SHOW
    with pytest.raises(ValueError):
        record_outcome(monday_booking, AppointmentStatus.CANCELLED, after)


def test_cancelled_booking_has_no_outcome(monday_booking):
    cancel_booking(monday_booking, NOW)
    with pytest.raises(CannotChange):
        record_outcome(monday_booking, AppointmentStatus.COMPLETED, monday_booking.end_at)


# Guest pages


@pytest.fixture
def open_shop(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    return shop_setup


def guest_books(client, setup, start="10:00"):
    response = client.post("/s/fade-street/", data=booking_data(setup, next_monday(), start=start))
    return response.headers["Location"].split("?")[0]  # /s/fade-street/booking/<token>


def test_guest_cancels_with_their_link(client, db, open_shop):
    link = guest_books(client, open_shop)
    page = client.get(link).get_data(as_text=True)
    assert "Change the time" in page and "Yes, cancel it" in page

    response = client.post(f"{link}/cancel")
    assert response.headers["Location"] == link
    assert db.session.scalar(select(Appointment)).status == AppointmentStatus.CANCELLED
    page = client.get(link).get_data(as_text=True)
    assert "This booking was cancelled" in page
    assert "Change the time" not in page

    client.post(f"{link}/cancel")
    assert "can&#39;t be cancelled online any more" in client.get(link).get_data(as_text=True)


def test_guest_moves_their_booking(client, db, open_shop):
    link = guest_books(client, open_shop)
    day = next_monday().isoformat()
    page = client.get(f"{link}/reschedule", query_string={"day": day}).get_data(as_text=True)
    assert "Move your booking" in page
    assert 'value="10:00"' in page  # its own time still counts as free

    response = client.post(
        f"{link}/reschedule",
        data={"barber": str(open_shop["member"].id), "day": day, "start": "11:00"},
    )
    assert response.headers["Location"] == link
    a = db.session.scalar(select(Appointment))
    assert to_local(a.start_at, "Europe/Bucharest").strftime("%H:%M") == "11:00"
    assert "11:00 to 11:30" in client.get(link).get_data(as_text=True)


def test_guest_cannot_move_into_a_taken_time(client, db, open_shop):
    link = guest_books(client, open_shop)
    guest_books(client, open_shop, start="11:00")
    day = next_monday().isoformat()
    response = client.post(
        f"{link}/reschedule",
        data={"barber": str(open_shop["member"].id), "day": day, "start": "11:00"},
    )
    assert response.status_code == 200
    assert b"Pick a new time first." in response.data


def test_wrong_link_cannot_cancel(client, db, open_shop):
    guest_books(client, open_shop)
    assert client.post("/s/fade-street/booking/not-a-token/cancel").status_code == 404
    assert db.session.scalar(select(Appointment)).status == AppointmentStatus.CONFIRMED


# Shop calendar and bookings


def make_bookings(client, db, setup):
    """A 10:00 booking with the owner (Ion Pop) and one with Radu (Radu's guest)."""
    guest_books(client, setup, start="10:00")
    data = booking_data(setup, next_monday(), start="10:00", barber=str(setup["radu"].id))
    data["guest_name"] = "Radu's guest"
    client.post("/s/fade-street/", data=data)

    def by_name(name):
        return db.session.scalar(select(Appointment).where(Appointment.guest_name == name))

    return by_name("Ion Pop"), by_name("Radu's guest")


@pytest.fixture
def team(db, open_shop):
    radu_user = make_user(db, "radu@example.com", Role.BARBER, name="Radu")
    radu = ShopMember(shop=open_shop["shop"], user=radu_user, display_name="Radu")
    db.session.add(radu)
    add_hours(db, radu, 0, (time(9), time(12)))
    open_shop["radu"] = radu
    return open_shop


def test_owner_sees_every_booking_on_the_calendar(client, db, team):
    make_bookings(client, db, team)
    login(client)
    page = client.get(
        "/shops/fade-street/calendar", query_string={"day": next_monday().isoformat()}
    ).get_data(as_text=True)
    assert "Ion Pop" in page and "Radu&#39;s guest" in page
    assert "09:00–12:00" in page


def test_barber_sees_only_their_own_bookings(client, db, team):
    owner_booking, radu_booking = make_bookings(client, db, team)
    login(client, "radu@example.com")
    page = client.get(
        "/shops/fade-street/calendar", query_string={"day": next_monday().isoformat()}
    ).get_data(as_text=True)
    assert "Radu&#39;s guest" in page and "Ion Pop" not in page
    assert client.get(f"/shops/fade-street/appointments/{owner_booking.id}").status_code == 404
    assert client.get(f"/shops/fade-street/appointments/{radu_booking.id}").status_code == 200


def test_outsider_gets_404_for_the_calendar(client, db, team):
    make_user(db, "other@example.com", Role.OWNER)
    login(client, "other@example.com")
    assert client.get("/shops/fade-street/calendar").status_code == 404


def test_calendar_needs_login(client, team):
    assert client.get("/shops/fade-street/calendar").status_code == 302


def test_owner_cancels_a_booking(client, db, team):
    _, radu_booking = make_bookings(client, db, team)
    login(client)
    url = f"/shops/fade-street/appointments/{radu_booking.id}"
    assert b"Move to another time" in client.get(url).data
    client.post(f"{url}/cancel")
    db.session.refresh(radu_booking)
    assert radu_booking.status == AppointmentStatus.CANCELLED


def test_barber_moves_own_booking_but_not_to_someone_else(client, db, team):
    _, radu_booking = make_bookings(client, db, team)
    login(client, "radu@example.com")
    url = f"/shops/fade-street/appointments/{radu_booking.id}/reschedule"
    day = next_monday().isoformat()
    page = client.get(url, query_string={"day": day}).get_data(as_text=True)
    assert "Any barber" not in page

    owner_member = team["member"].id
    response = client.post(url, data={"barber": str(owner_member), "day": day, "start": "11:00"})
    assert b"Pick a new time first." in response.data

    response = client.post(url, data={"barber": str(team["radu"].id), "day": day, "start": "11:00"})
    assert response.status_code == 302
    db.session.refresh(radu_booking)
    assert to_local(radu_booking.start_at, "Europe/Bucharest").strftime("%H:%M") == "11:00"
    assert radu_booking.member_id == team["radu"].id


def test_owner_moves_a_booking_to_another_barber(client, db, team):
    owner_booking, _ = make_bookings(client, db, team)
    login(client)
    url = f"/shops/fade-street/appointments/{owner_booking.id}/reschedule"
    day = next_monday().isoformat()
    client.post(url, data={"barber": str(team["radu"].id), "day": day, "start": "11:30"})
    db.session.refresh(owner_booking)
    assert owner_booking.member_id == team["radu"].id


def test_outcome_buttons(client, db, team):
    past_start = utcnow() - timedelta(hours=2)
    past = make_appointment(team, past_start, past_start + timedelta(minutes=30))
    db.session.add(past)
    db.session.commit()
    future, _ = make_bookings(client, db, team)
    login(client)

    page = client.get(f"/shops/fade-street/appointments/{past.id}").get_data(as_text=True)
    assert "How did it go?" in page and "Move to another time" not in page
    client.post(f"/shops/fade-street/appointments/{past.id}/no-show")
    db.session.refresh(past)
    assert past.status == AppointmentStatus.NO_SHOW

    client.post(f"/shops/fade-street/appointments/{future.id}/completed")
    db.session.refresh(future)
    assert future.status == AppointmentStatus.CONFIRMED


# Time off


def time_off_data(day, start="09:00", end="11:00", reason="Dentist"):
    return {
        "start": f"{day.isoformat()}T{start}",
        "end": f"{day.isoformat()}T{end}",
        "reason": reason,
    }


def test_time_off_hides_times_from_the_booking_page(client, db, open_shop):
    login(client)
    member = open_shop["member"]
    url = f"/shops/fade-street/barbers/{member.id}/time-off"
    day = next_monday()
    response = client.post(url, data=time_off_data(day))
    assert response.headers["Location"] == url
    assert "Dentist" in client.get(url).get_data(as_text=True)

    page = client.get(
        "/s/fade-street/",
        query_string={
            "service": open_shop["service"].id,
            "barber": member.id,
            "day": day.isoformat(),
        },
    ).get_data(as_text=True)
    assert 'value="10:00"' not in page and 'value="11:00"' in page

    entry = db.session.scalar(select(TimeOff))
    client.post(f"{url}/{entry.id}/delete")
    assert db.session.scalar(select(TimeOff)) is None


def test_time_off_warns_about_existing_bookings(client, db, open_shop):
    guest_books(client, open_shop, start="10:00")
    login(client)
    url = f"/shops/fade-street/barbers/{open_shop['member'].id}/time-off"
    client.post(url, data=time_off_data(next_monday()))
    page = client.get(url).get_data(as_text=True)
    assert "1 booking is already in that time" in page
    assert db.session.scalar(select(Appointment)).status == AppointmentStatus.CONFIRMED


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"start": "2026-11-02T11:00", "end": "2026-11-02T09:00"}, b"End after it starts."),
        ({"start": "2020-01-01T09:00", "end": "2020-01-01T11:00"}, b"Pick a time in the future."),
        ({"start": "", "end": "2026-11-02T09:00"}, b"Pick when it starts."),
    ],
)
def test_time_off_validation(client, db, open_shop, data, message):
    login(client)
    url = f"/shops/fade-street/barbers/{open_shop['member'].id}/time-off"
    response = client.post(url, data=data)
    assert response.status_code == 200
    assert message in response.data
    assert db.session.scalar(select(TimeOff)) is None


def test_barber_cannot_manage_someone_elses_time_off(client, team):
    login(client, "radu@example.com")
    own = f"/shops/fade-street/barbers/{team['radu'].id}/time-off"
    other = f"/shops/fade-street/barbers/{team['member'].id}/time-off"
    assert client.get(own).status_code == 200
    assert client.get(other).status_code == 404


def test_dashboard_links(client, team):
    login(client, "radu@example.com")
    page = client.get("/shops/").get_data(as_text=True)
    assert "/shops/fade-street/calendar" in page
    assert f"/shops/fade-street/barbers/{team['radu'].id}/time-off" in page


def test_booking_link_text_mentions_changing(client, open_shop):
    response = client.post("/s/fade-street/", data=booking_data(open_shop, next_monday()))
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert re.search(r"Use it to change or cancel", page)


def test_reschedule_page_opens_on_the_bookings_day(client, open_shop):
    link = guest_books(client, open_shop)
    page = client.get(f"{link}/reschedule").get_data(as_text=True)
    day = next_monday()
    assert f"{day.strftime('%A')} {day.day} {day.strftime('%B')}" in page
    assert re.search(rf'value="{day.isoformat()}" data-refresh\s+checked', page)
