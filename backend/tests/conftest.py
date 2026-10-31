import pytest

from app import create_app
from app.extensions import db as _db
from app.extensions import limiter
from app.models import Role, Service, Shop, ShopMember, User


@pytest.fixture
def app():
    app = create_app("testing")
    limiter.reset()  # limits are on in tests too; every test starts with fresh counters
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def shop_setup(db):
    """An owner with one shop, one barber membership and one service."""
    owner = User(email="owner@example.com", name="Owner", role=Role.OWNER)
    owner.set_password("secret-pass")
    shop = Shop(owner=owner, name="Fade Street", slug="fade-street")
    member = ShopMember(shop=shop, user=owner, display_name="Owner")
    service = Service(shop=shop, name="Haircut", duration_min=30, price_cents=5000)
    db.session.add_all([owner, shop, member, service])
    db.session.commit()
    return {"owner": owner, "shop": shop, "member": member, "service": service}


def make_appointment(setup, start, end, **overrides):
    from app.models import Appointment
    from app.security import generate_token, hash_token

    fields = dict(
        shop=setup["shop"],
        member=setup["member"],
        service=setup["service"],
        start_at=start,
        end_at=end,
        guest_name="Guest",
        guest_email="guest@example.com",
        guest_phone="+40700000000",
        manage_token_hash=hash_token(generate_token()),
    )
    fields.update(overrides)
    return Appointment(**fields)


def login(client, email="owner@example.com", password="secret-pass"):
    return client.post("/auth/login", data={"email": email, "password": password})


def make_user(db, email, role, name="Someone", password="secret-pass"):
    user = User(email=email, name=name, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user
