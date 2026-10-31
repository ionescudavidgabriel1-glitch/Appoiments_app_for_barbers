"""Web hardening and error pages.

- Security headers on every response, including a Content Security Policy that
  only allows the app's own scripts (no inline scripts, no code from strings).
- Private pages (logged in, or a guest's booking link) are never cached.
- Friendly error pages in the app's style for 400, 403, 404, 405, 429 and 500.
"""

import logging

from flask import Flask, render_template, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .extensions import db

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        # Inline style attributes set animation delays (style="--i: 3").
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
    ]
)

ERRORS = {
    400: ("Something in that request didn't work", "Go back and try again."),
    403: ("This page isn't yours", "You're logged in, but this page belongs to someone else."),
    404: ("We can't find that page", "The link may be old or mistyped."),
    405: ("That doesn't work here", "Go back and use the buttons on the page."),
    429: ("Slow down a little", "Too many tries in a short time. Wait a minute, then try again."),
    500: ("Something went wrong on our side", "It's not you. Please try again in a moment."),
}


def install(app: Flask) -> None:
    if app.config.get("TRUST_PROXY"):
        # Render puts the app behind a proxy: trust its X-Forwarded-* headers once,
        # so request.remote_addr is the visitor's IP and links use https.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    @app.after_request
    def security_headers(response):
        headers = response.headers
        headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        # Booking links carry a private token; never send them to other sites.
        headers.setdefault("Referrer-Policy", "same-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config.get("HSTS"):
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if current_user.is_authenticated or "/booking/" in request.path:
            headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_error(400, "This form expired", "Reload the page and try again.")

    @app.errorhandler(HTTPException)
    def http_error(error):
        if error.code not in ERRORS:
            return error
        return render_error(error.code, *ERRORS[error.code])

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_error(500, *ERRORS[500])


def render_error(code: int, title: str, message: str):
    return render_template("errors/error.html", code=code, title=title, message=message), code
