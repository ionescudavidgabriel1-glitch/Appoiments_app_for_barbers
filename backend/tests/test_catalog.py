import re
from datetime import time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.catalog import format_money, slugify, to_cents, unique_slug
from app.models import Invite, Role, Service, Shop, ShopMember, User, WorkingHours
from app.security import generate_token, hash_token
from app.timeutils import utcnow

from .conftest import login, make_user

SHOP_FORM = {"timezone": "Europe/Bucharest", "currency": "RON", "slot_minutes": "15"}


def add_invite(db, setup, expires_in=timedelta(days=7)):
    token = generate_token()
    db.session.add(
        Invite(
            shop=setup["shop"],
            created_by_id=setup["owner"].id,
            token_hash=hash_token(token),
            expires_at=utcnow() + expires_in,
        )
    )
    db.session.commit()
    return token


def hours_data(days):
    """days maps weekday -> (start1, end1, start2, end2); missing days are days off."""
    data = {}
    for day in range(7):
        values = days.get(day, ("", "", "", ""))
        for name, value in zip(("start1", "end1", "start2", "end2"), values, strict=True):
            data[f"days-{day}-{name}"] = value
    return data


# Helpers


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Fade Street", "fade-street"),
        ("Frizeria Ștefan & Co", "frizeria-stefan-co"),
        ("  --Hello__World--  ", "hello-world"),
        ("!!!", ""),
    ],
)
def test_slugify(name, slug):
    assert slugify(name) == slug


def test_unique_slug_adds_number_when_taken(shop_setup):
    assert unique_slug("Fade Street") == "fade-street-2"
    assert unique_slug("New Place") == "new-place"
    assert unique_slug("!!") == "shop"
    assert unique_slug("Al") == "al-shop"


@pytest.mark.parametrize(
    ("amount", "cents"),
    [(None, 0), (Decimal("0"), 0), (Decimal("50"), 5000), (Decimal("12.345"), 1235)],
)
def test_to_cents(amount, cents):
    assert to_cents(amount) == cents


def test_format_money():
    assert format_money(5000, "RON") == "50.00 RON"
    assert format_money(1205, "EUR") == "12.05 EUR"


# Shops


def test_owner_creates_shop_with_generated_slug(client, db):
    make_user(db, "new@example.com", Role.OWNER)
    login(client, "new@example.com")
    response = client.post("/shops/new", data={"name": "Frizeria Ștefan", **SHOP_FORM})
    assert response.headers["Location"] == "/shops/frizeria-stefan/"
    shop = db.session.scalar(select(Shop).where(Shop.slug == "frizeria-stefan"))
    assert shop.owner.email == "new@example.com"
    assert shop.slot_minutes == 15


def test_create_shop_rejects_taken_slug(client, shop_setup):
    login(client)
    response = client.post("/shops/new", data={"name": "Copy", "slug": "fade-street", **SHOP_FORM})
    assert response.status_code == 200
    assert b"Another shop already uses this address" in response.data


@pytest.mark.parametrize("slug", ["fade street", "ab", "fade--street", "-fade"])
def test_create_shop_rejects_bad_slug(client, db, shop_setup, slug):
    login(client)
    response = client.post("/shops/new", data={"name": "X", "slug": slug, **SHOP_FORM})
    assert response.status_code == 200
    assert len(db.session.scalars(select(Shop)).all()) == 1


def test_create_shop_lowercases_slug(client, db, shop_setup):
    login(client)
    client.post("/shops/new", data={"name": "X", "slug": "  My-Shop ", **SHOP_FORM})
    assert db.session.scalar(select(Shop).where(Shop.slug == "my-shop")) is not None


def test_barber_cannot_create_shop(client, db):
    make_user(db, "barber@example.com", Role.BARBER)
    login(client, "barber@example.com")
    assert client.get("/shops/new").status_code == 403


def test_edit_shop_settings(client, db, shop_setup):
    login(client)
    response = client.post(
        "/shops/fade-street/settings",
        data={
            "name": "Fade Street Two",
            "slug": "fade-two",
            "address": "Str. Lunga 1",
            "timezone": "Europe/London",
            "currency": "EUR",
            "slot_minutes": "30",
        },
    )
    assert response.headers["Location"] == "/shops/fade-two/"
    shop = shop_setup["shop"]
    db.session.refresh(shop)
    assert (shop.name, shop.slug, shop.timezone, shop.currency, shop.slot_minutes) == (
        "Fade Street Two",
        "fade-two",
        "Europe/London",
        "EUR",
        30,
    )


def test_edit_shop_keeps_slug_when_left_empty(client, db, shop_setup):
    login(client)
    client.post("/shops/fade-street/settings", data={"name": "Renamed", "slug": "", **SHOP_FORM})
    shop = shop_setup["shop"]
    db.session.refresh(shop)
    assert (shop.name, shop.slug) == ("Renamed", "fade-street")


def test_other_owner_gets_404_for_shop_pages(client, db, shop_setup):
    make_user(db, "other@example.com", Role.OWNER)
    login(client, "other@example.com")
    service_id = shop_setup["service"].id
    member_id = shop_setup["member"].id
    assert client.get("/shops/fade-street/").status_code == 404
    assert client.get("/shops/fade-street/settings").status_code == 404
    assert client.get(f"/shops/fade-street/services/{service_id}/edit").status_code == 404
    assert client.post(f"/shops/fade-street/services/{service_id}/toggle").status_code == 404
    assert client.post("/shops/fade-street/invites").status_code == 404
    assert client.get(f"/shops/fade-street/barbers/{member_id}/hours").status_code == 404


def test_overview_lists_services_and_barbers(client, shop_setup):
    login(client)
    response = client.get("/shops/fade-street/")
    assert response.status_code == 200
    assert b"Haircut" in response.data
    assert b"50.00 RON" in response.data
    assert b"No hours set" in response.data


# Services


def test_create_service(client, db, shop_setup):
    login(client)
    response = client.post(
        "/shops/fade-street/services/new",
        data={"name": "Beard trim", "duration_min": "20", "price": "35.5"},
    )
    assert response.headers["Location"] == "/shops/fade-street/"
    service = db.session.scalar(select(Service).where(Service.name == "Beard trim"))
    assert (service.duration_min, service.price_cents, service.active) == (20, 3550, True)


def test_create_free_service(client, db, shop_setup):
    login(client)
    client.post("/shops/fade-street/services/new", data={"name": "Consult", "duration_min": "10"})
    service = db.session.scalar(select(Service).where(Service.name == "Consult"))
    assert service.price_cents == 0


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"name": "", "duration_min": "30"}, b"Enter a name"),
        ({"name": "X", "duration_min": "33"}, b"multiple of 5"),
        ({"name": "X", "duration_min": "0"}, b"how long it takes"),
        ({"name": "X", "duration_min": "500"}, b"between 5 and 480"),
        ({"name": "X", "duration_min": "30", "price": "-1"}, b"price from 0"),
    ],
)
def test_service_validation(client, shop_setup, data, message):
    login(client)
    response = client.post("/shops/fade-street/services/new", data=data)
    assert response.status_code == 200
    assert message in response.data


def test_edit_service_prefills_price_and_saves(client, db, shop_setup):
    login(client)
    url = f"/shops/fade-street/services/{shop_setup['service'].id}/edit"
    assert b'value="50.00"' in client.get(url).data
    client.post(url, data={"name": "Haircut deluxe", "duration_min": "45", "price": "70"})
    service = shop_setup["service"]
    db.session.refresh(service)
    assert (service.name, service.duration_min, service.price_cents) == (
        "Haircut deluxe",
        45,
        7000,
    )


def test_toggle_service(client, db, shop_setup):
    login(client)
    service = shop_setup["service"]
    client.post(f"/shops/fade-street/services/{service.id}/toggle")
    db.session.refresh(service)
    assert service.active is False
    client.post(f"/shops/fade-street/services/{service.id}/toggle")
    db.session.refresh(service)
    assert service.active is True


def test_service_of_other_shop_is_404(client, db, shop_setup):
    other_owner = make_user(db, "other@example.com", Role.OWNER)
    other_shop = Shop(owner=other_owner, name="Other", slug="other")
    other_service = Service(shop=other_shop, name="X", duration_min=30)
    db.session.add_all([other_shop, other_service])
    db.session.commit()
    login(client)
    assert client.get(f"/shops/fade-street/services/{other_service.id}/edit").status_code == 404


# Invites


def create_invite_link(client):
    client.post("/shops/fade-street/invites")
    page = client.get("/shops/fade-street/").get_data(as_text=True)
    return re.search(r'id="invite-link"[^>]*value="([^"]+)"', page).group(1)


def test_invite_link_is_shown_once_and_only_hash_is_stored(client, db, shop_setup):
    login(client)
    link = create_invite_link(client)
    token = link.rsplit("/", 1)[1]
    invite = db.session.scalar(select(Invite))
    assert invite.token_hash == hash_token(token)
    assert invite.token_hash != token
    assert b"invite-link" not in client.get("/shops/fade-street/").data


def test_new_barber_accepts_invite(client, db, shop_setup):
    login(client)
    path = create_invite_link(client).replace("http://localhost", "")
    client.post("/auth/logout")

    assert b"Join Fade Street" in client.get(path).data
    response = client.post(
        path,
        data={
            "name": "Mihai",
            "email": "mihai@example.com",
            "password": "long-password",
            "confirm": "long-password",
        },
    )
    assert response.headers["Location"] == "/shops/"
    barber = db.session.scalar(select(User).where(User.email == "mihai@example.com"))
    assert barber.role == Role.BARBER
    assert [m.shop.slug for m in barber.memberships] == ["fade-street"]
    invite = db.session.scalar(select(Invite))
    assert invite.used_by_id == barber.id

    client.post("/auth/logout")
    assert client.get(path).status_code == 404  # single use


def test_invite_signup_rejects_existing_email(client, db, shop_setup):
    token = add_invite(db, shop_setup)
    response = client.post(
        f"/auth/invite/{token}",
        data={
            "name": "X",
            "email": "owner@example.com",
            "password": "long-password",
            "confirm": "long-password",
        },
    )
    assert b"Log in to join" in response.data
    assert db.session.scalar(select(Invite)).used_at is None


def test_logged_in_barber_joins_another_shop(client, db, shop_setup):
    barber = make_user(db, "barber@example.com", Role.BARBER, name="Radu")
    token = add_invite(db, shop_setup)
    login(client, "barber@example.com")
    assert b"join as Radu" in client.get(f"/auth/invite/{token}").data
    client.post(f"/auth/invite/{token}")
    db.session.refresh(barber)
    assert [m.display_name for m in barber.memberships] == ["Radu"]


def test_existing_member_is_told_they_already_joined(client, db, shop_setup):
    token = add_invite(db, shop_setup)
    login(client)  # the owner is already a member of Fade Street
    assert b"already on the team" in client.get(f"/auth/invite/{token}").data


def test_expired_invite_is_rejected(client, db, shop_setup):
    token = add_invite(db, shop_setup, expires_in=timedelta(seconds=-1))
    response = client.get(f"/auth/invite/{token}")
    assert response.status_code == 404
    assert b"invite link doesn" in response.data


def test_unknown_invite_is_rejected(client, shop_setup):
    assert client.get("/auth/invite/not-a-real-token").status_code == 404


def test_revoke_invite(client, db, shop_setup):
    token = add_invite(db, shop_setup)
    invite = db.session.scalar(select(Invite))
    login(client)
    client.post(f"/shops/fade-street/invites/{invite.id}/revoke")
    client.post("/auth/logout")
    assert client.get(f"/auth/invite/{token}").status_code == 404


# Barbers


def test_owner_adds_self_as_barber_once(client, db):
    owner = make_user(db, "solo@example.com", Role.OWNER, name="Solo")
    db.session.add(Shop(owner=owner, name="Solo Cuts", slug="solo-cuts"))
    db.session.commit()
    login(client, "solo@example.com")
    response = client.post("/shops/solo-cuts/barbers/add-me")
    assert "/hours" in response.headers["Location"]
    client.post("/shops/solo-cuts/barbers/add-me")
    assert len(db.session.scalars(select(ShopMember)).all()) == 1


def test_toggle_member(client, db, shop_setup):
    login(client)
    member = shop_setup["member"]
    client.post(f"/shops/fade-street/barbers/{member.id}/toggle")
    db.session.refresh(member)
    assert member.active is False


# Working hours


def test_owner_saves_hours_with_break(client, db, shop_setup):
    login(client)
    url = f"/shops/fade-street/barbers/{shop_setup['member'].id}/hours"
    response = client.post(
        url,
        data=hours_data({0: ("09:00", "13:00", "14:00", "18:00"), 5: ("10:00", "14:00", "", "")}),
    )
    assert response.headers["Location"] == "/shops/fade-street/"
    rows = db.session.scalars(
        select(WorkingHours).order_by(WorkingHours.weekday, WorkingHours.start_time)
    ).all()
    assert [(r.weekday, r.start_time, r.end_time) for r in rows] == [
        (0, time(9), time(13)),
        (0, time(14), time(18)),
        (5, time(10), time(14)),
    ]
    assert 'value="14:00"' in client.get(url).get_data(as_text=True)

    # Saving again replaces the old hours.
    client.post(url, data=hours_data({1: ("08:00", "12:00", "", "")}))
    rows = db.session.scalars(select(WorkingHours)).all()
    assert [(r.weekday, r.start_time) for r in rows] == [(1, time(8))]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (("09:00", "", "", ""), b"Fill in both times"),
        (("18:00", "09:00", "", ""), b"End after it starts"),
        (("09:00", "13:00", "12:00", "18:00"), b"after the first one ends"),
        (("", "", "14:00", "18:00"), b"first shift first"),
    ],
)
def test_hours_validation(client, db, shop_setup, values, message):
    login(client)
    url = f"/shops/fade-street/barbers/{shop_setup['member'].id}/hours"
    response = client.post(url, data=hours_data({2: values}))
    assert response.status_code == 200
    assert message in response.data
    assert db.session.scalars(select(WorkingHours)).all() == []


def test_barber_edits_own_hours_but_not_others(client, db, shop_setup):
    barber = make_user(db, "barber@example.com", Role.BARBER, name="Radu")
    own = ShopMember(shop=shop_setup["shop"], user=barber, display_name="Radu")
    db.session.add(own)
    db.session.commit()
    login(client, "barber@example.com")

    response = client.post(
        f"/shops/fade-street/barbers/{own.id}/hours",
        data=hours_data({0: ("09:00", "17:00", "", "")}),
    )
    assert response.headers["Location"] == "/shops/"
    other = shop_setup["member"].id
    assert client.get(f"/shops/fade-street/barbers/{other}/hours").status_code == 404
    assert client.get("/shops/fade-street/").status_code == 403


def test_dashboard_links_to_shop_and_hours(client, shop_setup):
    login(client)
    page = client.get("/shops/").get_data(as_text=True)
    assert 'href="/shops/fade-street/"' in page
    assert f"/shops/fade-street/barbers/{shop_setup['member'].id}/hours" in page
