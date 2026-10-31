from datetime import datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AppointmentStatus, Invite, Role, User, WorkingHours

from .conftest import make_appointment

START = datetime(2026, 11, 2, 9, 0)


def test_password_is_hashed(shop_setup):
    owner = shop_setup["owner"]
    assert owner.password_hash != "secret-pass"
    assert owner.check_password("secret-pass")
    assert not owner.check_password("wrong")


def test_user_email_is_unique(db, shop_setup):
    dup = User(email="owner@example.com", name="Other", role=Role.BARBER)
    dup.set_password("x")
    db.session.add(dup)
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_invalid_role_is_rejected(db):
    user = User(email="a@example.com", name="A", role="customer")
    user.set_password("x")
    db.session.add(user)
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_foreign_keys_are_enforced(db):
    db.session.add(WorkingHours(member_id=999, weekday=0, start_time=time(9), end_time=time(17)))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_working_hours_must_end_after_start(db, shop_setup):
    db.session.add(
        WorkingHours(member=shop_setup["member"], weekday=0, start_time=time(17), end_time=time(9))
    )
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_appointment_must_end_after_start(db, shop_setup):
    db.session.add(make_appointment(shop_setup, START, START))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_same_barber_same_start_is_rejected(db, shop_setup):
    end = START + timedelta(minutes=30)
    db.session.add(make_appointment(shop_setup, START, end))
    db.session.commit()
    db.session.add(make_appointment(shop_setup, START, end))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_cancelled_slot_can_be_rebooked(db, shop_setup):
    end = START + timedelta(minutes=30)
    db.session.add(make_appointment(shop_setup, START, end, status=AppointmentStatus.CANCELLED))
    db.session.commit()
    db.session.add(make_appointment(shop_setup, START, end))
    db.session.commit()


def test_invite_usability(shop_setup):
    now = datetime(2026, 11, 1, 12, 0)
    invite = Invite(
        shop=shop_setup["shop"],
        created_by_id=shop_setup["owner"].id,
        token_hash="x" * 64,
        expires_at=now + timedelta(days=7),
    )
    assert invite.is_usable(now)
    assert not invite.is_usable(now + timedelta(days=8))
    invite.used_at = now
    assert not invite.is_usable(now)
