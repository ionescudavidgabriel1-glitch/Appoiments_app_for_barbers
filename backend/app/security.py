"""Random tokens for invite links and guest booking links.

The raw token goes only into the link sent to the person. The database stores
its SHA-256 hash, so a leaked database cannot be used to open those links.
"""

import hashlib
import hmac
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), stored_hash)
