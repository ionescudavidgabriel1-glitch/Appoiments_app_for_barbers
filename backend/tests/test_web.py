import re
from datetime import time

import pytest

from app import create_app
from app.models import Role

from .conftest import login, make_user
from .test_booking import add_hours, booking_data, next_monday

# Security headers and scripts


def test_security_headers(client):
    headers = client.get("/").headers
    csp = headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-eval" not in csp
    assert "frame-ancestors 'none'" in csp
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    assert "Strict-Transport-Security" not in headers  # only in production


@pytest.fixture
def open_shop(db, shop_setup):
    add_hours(db, shop_setup["member"], 0, (time(9), time(12)))
    return shop_setup


def test_pages_have_no_inline_or_outside_scripts(client, open_shop):
    link = client.post("/s/fade-street/", data=booking_data(open_shop, next_monday()))
    public = ["/", "/auth/login", "/auth/signup", "/s/fade-street/", link.headers["Location"]]
    private = ["/shops/", "/shops/fade-street/", "/shops/fade-street/calendar"]
    pages = [(path, client.get(path)) for path in public]
    login(client)
    pages += [(path, client.get(path)) for path in private]
    for path, response in pages:
        assert response.status_code == 200, path
        html = response.get_data(as_text=True)
        scripts = re.findall(r"<script[^>]*>", html)
        assert scripts, path
        assert all(re.search(r'src="/static/', tag) for tag in scripts), (path, scripts)
        assert not re.search(r"\son(click|change|submit|load)=", html), path
        assert "unpkg.com" not in html and "cdn.tailwindcss.com" not in html, path


def test_private_pages_are_not_cached(client, open_shop):
    assert "Cache-Control" not in client.get("/").headers
    link = client.post("/s/fade-street/", data=booking_data(open_shop, next_monday()))
    assert client.get(link.headers["Location"]).headers["Cache-Control"] == "no-store"
    login(client)
    assert client.get("/shops/").headers["Cache-Control"] == "no-store"


def test_static_files_are_served(client):
    assert client.get("/static/css/tailwind.css").status_code == 200
    assert client.get("/static/vendor/htmx-2.0.4.min.js").status_code == 200
    assert client.get("/static/favicon.svg").status_code == 200


def test_health_check(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


# Error pages


def test_404_page(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert b"We can&#39;t find that page" in response.data
    assert b"Go to the home page" in response.data


def test_403_page(client, db):
    make_user(db, "barber@example.com", Role.BARBER)
    login(client, "barber@example.com")
    response = client.get("/shops/new")
    assert response.status_code == 403
    assert b"This page isn&#39;t yours" in response.data
    assert b"Your dashboard" in response.data


def test_405_page(client):
    response = client.get("/auth/logout")
    assert response.status_code == 405
    assert b"That doesn&#39;t work here" in response.data


def test_expired_form_page(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post("/auth/login", data={"email": "a@example.com", "password": "x"})
    assert response.status_code == 400
    assert b"This form expired" in response.data


def test_500_page(app, client):
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    response = client.get("/boom")
    assert response.status_code == 500
    assert b"Something went wrong on our side" in response.data


# Limits


def test_login_attempts_are_limited(client, shop_setup):
    for _ in range(10):
        assert login(client, password="wrong-password").status_code == 200
    response = login(client, password="wrong-password")
    assert response.status_code == 429
    assert b"Slow down a little" in response.data
    # Looking at the login page is never limited.
    assert client.get("/auth/login").status_code == 200


# Production settings


def test_production_uses_https_settings(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    app = create_app("production")

    @app.get("/whoami")
    def whoami():
        from flask import request, url_for

        return {"ip": request.remote_addr, "url": url_for("main.home", _external=True)}

    client = app.test_client()
    response = client.get(
        "/",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.7"},
    )
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")

    data = client.get(
        "/whoami",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.7"},
    ).json
    assert data["ip"] == "203.0.113.7"
    assert data["url"].startswith("https://")
