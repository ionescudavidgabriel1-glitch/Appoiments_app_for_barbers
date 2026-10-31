"""Random tokens for invite links and guest booking links.

The raw token goes only into the link sent to the person. The database stores
its SHA-256 hash, so a leaked database cannot be used to open those links.

Booking links must also appear in later emails (reminders, changes), so their
token is derived from a random per-booking nonce and the app's SECRET_KEY. The
app can rebuild the link; someone with only the database cannot.
"""

import base64
import hashlib
import hmac
import secrets

from flask import current_app


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), stored_hash)


def new_booking_token() -> tuple[str, str]:
    """A fresh (nonce, token) pair for a booking's manage link."""
    nonce = secrets.token_hex(16)
    return nonce, booking_token(nonce)


def booking_token(nonce: str) -> str:
    key = current_app.config["SECRET_KEY"].encode()
    digest = hmac.new(key, f"booking:{nonce}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
