from datetime import datetime

from app.security import generate_token, hash_token, token_matches
from app.timeutils import to_local, to_utc


def test_token_round_trip():
    token = generate_token()
    stored = hash_token(token)
    assert stored != token
    assert token_matches(token, stored)
    assert not token_matches(generate_token(), stored)


def test_bucharest_conversion_winter():
    # Bucharest is UTC+2 in winter.
    utc = to_utc(datetime(2026, 1, 15, 10, 0), "Europe/Bucharest")
    assert utc == datetime(2026, 1, 15, 8, 0)
    assert to_local(utc, "Europe/Bucharest").replace(tzinfo=None) == datetime(2026, 1, 15, 10, 0)


def test_bucharest_conversion_summer():
    # Bucharest is UTC+3 in summer.
    assert to_utc(datetime(2026, 7, 15, 10, 0), "Europe/Bucharest") == datetime(2026, 7, 15, 7, 0)
