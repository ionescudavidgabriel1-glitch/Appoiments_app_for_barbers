# Changelog

Each build phase is released as one version. See "Versioning" in `CLAUDE.md`.

## v0.1.0 - Phase 1: Foundation (2026-10-31)

- Flask app factory with blueprints: main, auth, shops, admin, booking.
- Config from environment variables, for development, testing and production.
- Data models: User, Shop, ShopMember, Invite, Service, WorkingHours, TimeOff, Appointment.
- Initial database migration, with named constraints and foreign keys enforced on SQLite.
- Database guard against two active bookings with the same barber at the same start time.
- Home page with a base layout (Jinja and Tailwind CSS).
- pytest suite for config, the home page, model constraints and helpers.
- Root, backend and frontend READMEs.
