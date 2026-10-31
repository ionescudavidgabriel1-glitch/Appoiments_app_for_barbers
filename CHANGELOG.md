# Changelog

Each build phase is released as one version. See "Versioning" in `CLAUDE.md`.

## v0.2.0 - Phase 2: Accounts (2026-10-31)

- Owner sign up, login with "keep me logged in", and logout.
- Case-insensitive emails, minimum password length of 8, hashed passwords.
- Same error message for an unknown email and a wrong password.
- Redirect after login only to paths on this site.
- Logout by POST with a CSRF token.
- `role_required` decorator for role-based access (403 for other roles).
- Dashboard listing the user's shops and memberships.
- Header navigation with login, sign up and logout; reusable form macros.
- Tests for sign up, login, logout, CSRF, redirects and access control.

## v0.1.0 - Phase 1: Foundation (2026-10-31)

- Flask app factory with blueprints: main, auth, shops, admin, booking.
- Config from environment variables, for development, testing and production.
- Data models: User, Shop, ShopMember, Invite, Service, WorkingHours, TimeOff, Appointment.
- Initial database migration, with named constraints and foreign keys enforced on SQLite.
- Database guard against two active bookings with the same barber at the same start time.
- Home page with a base layout (Jinja and Tailwind CSS).
- pytest suite for config, the home page, model constraints and helpers.
- Root, backend and frontend READMEs.
