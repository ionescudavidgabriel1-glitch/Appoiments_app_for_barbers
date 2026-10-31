import pytest

from app import create_app
from app.config import ProductionConfig, _database_url


def test_testing_config(app):
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Online booking for your barbershop" in response.data


def test_unknown_page_returns_404(client):
    assert client.get("/no-such-page").status_code == 404


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        ProductionConfig.validate()


def test_production_app_starts_with_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    app = create_app("production")
    assert app.config["SESSION_COOKIE_SECURE"] is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "sqlite:///barbershop.db"),
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ],
)
def test_database_url_normalization(monkeypatch, raw, expected):
    monkeypatch.setenv("DATABASE_URL", raw)
    assert _database_url() == expected
