# Changelog

Each build phase is released as one version. See "Versioning" in `CLAUDE.md`.

## v0.3.0 - Phase 3: Catalog (2026-10-31)

- Owners create shops: name, booking page address (made from the name if left empty), address, phone, timezone, currency and booking time grid; editable in shop settings.
- Services with duration and price; hide and show instead of deleting.
- Barber invites: single-use links that expire after 7 days, shown once and stored only as a hash; owners can cancel unused links.
- Invited barbers create an account, or join with the account they have.
- Owners can add themselves as a barber; barbers can be hidden and shown.
- Weekly working hours per barber with an optional break, editable by the owner or the barber; "Copy Monday to Tuesday–Friday".
- Shop overview page; dashboard links to shops and working hours.
- Tests for shops, services, invites, barbers, working hours and access between shops.

## v0.2.1 - Design pass (2026-10-31)

- New look, "the appointment book": warm colors (towel, walnut, oxblood, chair mint, brass), Big Shoulders Display headings and Figtree text.
- Buttons lift on hover, squish on press, and primary buttons show barber-pole stripes.
- Submit buttons show a spinner and a loading label; flash messages slide in and fade out.
- Show/Hide for password fields; time-of-day greeting on the dashboard.
- Home page with a clickable sample appointment book; logo with a turning barber pole.
- Restyled home, sign up, login and dashboard pages; responsive down to phone width.
- Plain, friendly form error messages.
- All animation respects the "reduce motion" setting.
- Playwright added to dev requirements for page checks.

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
