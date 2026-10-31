import pytest
from flask import Blueprint
from sqlalchemy import select

from app.blueprints.auth import is_safe_next
from app.decorators import role_required
from app.models import Role, User


def signup(client, **overrides):
    data = {
        "name": "Ana Pop",
        "email": "ana@example.com",
        "password": "long-password",
        "confirm": "long-password",
    }
    data.update(overrides)
    return client.post("/auth/signup", data=data)


def login(client, email="owner@example.com", password="secret-pass", **extra):
    return client.post("/auth/login", data={"email": email, "password": password}, **extra)


# Sign up


def test_signup_creates_owner_and_logs_in(client, db):
    response = signup(client, email="  Ana@Example.COM ")
    assert response.status_code == 302
    assert response.headers["Location"] == "/shops/"

    user = db.session.scalar(select(User).where(User.email == "ana@example.com"))
    assert user is not None
    assert user.role == Role.OWNER
    assert user.check_password("long-password")
    assert client.get("/shops/").status_code == 200


def test_signup_rejects_duplicate_email_case_insensitive(client, shop_setup):
    response = signup(client, email="OWNER@example.com")
    assert response.status_code == 200
    assert b"already exists" in response.data


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"password": "short", "confirm": "short"}, b"Use at least 8 characters."),
        ({"confirm": "different-password"}, b"The two passwords don&#39;t match."),
        ({"email": "not-an-email"}, b"Enter an email like name@example.com."),
        ({"name": ""}, b"Enter your name."),
    ],
)
def test_signup_validation(client, db, overrides, message):
    response = signup(client, **overrides)
    assert response.status_code == 200
    assert message in response.data
    assert db.session.scalar(select(User)) is None


# Login and logout


def test_login_success_redirects_to_dashboard(client, shop_setup):
    response = login(client, email="Owner@Example.com")
    assert response.status_code == 302
    assert response.headers["Location"] == "/shops/"


@pytest.mark.parametrize(
    ("email", "password"),
    [("owner@example.com", "wrong-password"), ("nobody@example.com", "secret-pass")],
)
def test_login_failure_shows_same_message(client, shop_setup, email, password):
    response = login(client, email=email, password=password)
    assert response.status_code == 200
    assert b"Incorrect email or password." in response.data
    assert client.get("/shops/").status_code == 302


def test_login_follows_safe_next(client, shop_setup):
    response = login(client, query_string={"next": "/shops/"})
    assert response.headers["Location"] == "/shops/"


def test_login_ignores_unsafe_next(client, shop_setup):
    response = login(client, query_string={"next": "https://evil.example/"})
    assert response.headers["Location"] == "/shops/"


@pytest.mark.parametrize(
    ("target", "safe"),
    [
        ("/shops/", True),
        ("/s/fade-street?x=1", True),
        (None, False),
        ("", False),
        ("https://evil.example/", False),
        ("//evil.example/", False),
        (r"/\evil.example", False),
        ("shops", False),
    ],
)
def test_is_safe_next(target, safe):
    assert is_safe_next(target) is safe


def test_logout(client, shop_setup):
    login(client)
    response = client.post("/auth/logout")
    assert response.headers["Location"] == "/"
    assert client.get("/shops/").status_code == 302


def test_logout_requires_post(client, shop_setup):
    login(client)
    assert client.get("/auth/logout").status_code == 405


def test_logged_in_user_is_redirected_from_login_and_signup(client, shop_setup):
    login(client)
    assert client.get("/auth/login").headers["Location"] == "/shops/"
    assert client.get("/auth/signup").headers["Location"] == "/shops/"


# CSRF


def test_csrf_blocks_login_and_logout_without_token(app, client, shop_setup):
    login(client)
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post("/auth/logout")
    assert response.status_code == 400
    assert client.get("/shops/").status_code == 200  # still logged in


# Access control


def test_dashboard_requires_login(client):
    response = client.get("/shops/")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/login?next=")


def test_dashboard_lists_owned_shops(client, shop_setup):
    login(client)
    response = client.get("/shops/")
    assert b"Fade Street" in response.data


@pytest.fixture
def owner_only_client(app):
    bp = Blueprint("test_roles", __name__)

    @bp.get("/owner-only")
    @role_required(Role.OWNER)
    def owner_only():
        return "ok"

    app.register_blueprint(bp)
    return app.test_client()


def test_role_required_allows_matching_role(owner_only_client, shop_setup):
    login(owner_only_client)
    assert owner_only_client.get("/owner-only").status_code == 200


def test_role_required_forbids_other_roles(owner_only_client, db):
    barber = User(email="barber@example.com", name="Barber", role=Role.BARBER)
    barber.set_password("secret-pass")
    db.session.add(barber)
    db.session.commit()

    login(owner_only_client, email="barber@example.com")
    assert owner_only_client.get("/owner-only").status_code == 403


def test_role_required_redirects_anonymous_to_login(owner_only_client):
    assert owner_only_client.get("/owner-only").status_code == 302
