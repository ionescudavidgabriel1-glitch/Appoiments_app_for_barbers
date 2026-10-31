# Changelog

Each build phase is released as one version. See "Versioning" in `CLAUDE.md`.

## v1.0.0 - Phase 7: Polish and deploy (2026-11-01)

- Tailwind CSS built ahead of time into one small stylesheet (`npm run build:css`) instead of compiling in the browser; HTMX served by the app.
- Security headers on every page, including a strict Content Security Policy (only the app's own scripts); no inline scripts left. Private pages are never cached, and private booking links are never sent to other sites.
- Limits on login, sign-up and booking attempts, with a friendly "slow down" page.
- Friendly error pages for not found, not allowed, expired forms and server errors.
- Production: HTTPS-only cookies, HSTS, correct visitor IPs and https links behind Render's proxy, logs to standard output, emails logged when no mail server is set.
- `/healthz` health check, favicon.
- Render Blueprint (`render.yaml`): website, PostgreSQL and the reminders worker, with migrations on every deploy.
- GitHub Actions: lint and tests on every push, migrations and tests on PostgreSQL, and a check that the built CSS is up to date.
- Deploy guide in the README.

## v0.6.0 - Phase 6: Notifications (2026-10-31)

- Emails to guests: booking confirmation with the private link, moved, cancelled, and reminders 24 hours and 2 hours before.
- Emails to the barber: new booking, moved (including to or from another barber) and cancelled, except for changes they made themselves. Owners get no emails.
- Emails in the shop's language, Romanian or English, set automatically from the shop's timezone and changeable in shop settings. Flask-Babel is set up for the later interface translation.
- One warm HTML email layout with a plain-text version.
- Development saves emails as files in `backend/instance/outbox/`; production sends over SMTP (settings in `.env`). A failed email never blocks a booking.
- Reminders run in a separate process: `flask reminders-worker` (every 5 minutes) or `flask send-reminders` (once). Each reminder is sent only once, even with two workers.
- Booking links in later emails are rebuilt from a per-booking nonce and the secret key; the database still stores only their hash.
- Migration: `shops.language`, reminder timestamps and `appointments.manage_nonce`. Existing shops in Romania switch to Romanian.

## v0.5.0 - Phase 5: Management (2026-10-31)

- Daily calendar at `/shops/<shop>/calendar`: each barber's hours, time off and bookings, with previous/next day and a date picker. Owners see the whole shop; barbers see their own bookings.
- Booking page for the shop with the customer's phone and email; cancel, move to another time (owners can also move to another barber), and record completed or no-show after it starts.
- Guests can change the time or cancel through their private link, any time before the appointment starts.
- Rescheduling reuses the booking rules and safety checks; the booking's own old time counts as free, and the page opens on the booking's day.
- Time off per barber (holidays, sick days), editable by the owner or the barber; it hides those times from the booking page and warns about bookings already inside it.
- Booking steps shared between booking and reschedule pages (`booking/_steps.html`).
- Tests for cancel, reschedule, outcomes, access between owner, barbers and outsiders, and time off.

## v0.4.1 - Shifts until midnight (2026-10-31)

- Working hours can end at 00:00, meaning until midnight; customers can book the last slot before midnight.
- A shift that crosses midnight now gets a clear message: end at 00:00 and add the rest to the next day (instead of "End after it starts").
- Tests for midnight shifts in the hours form and the booking rules.

## v0.4.0 - Phase 4: Booking (2026-10-31)

- Public booking page at `/s/<shop-address>`: choose a service, a barber or "Any barber", a day and a free time, then enter name, email and phone. No account needed.
- Choices update in place with HTMX; the page still works without JavaScript.
- Booking rules in `app/booking.py`: times on the shop's grid, inside working hours, long enough for the service, in the future, within 30 days, and not overlapping other bookings or time off. Shop timezone and daylight saving handled.
- Double bookings prevented by re-checking inside the transaction (with a row lock on PostgreSQL) and the unique index; a guest who loses a race is asked to pick another time.
- Confirmation page with a private link to the booking (stored only as a hash).
- Owner pages link to the shop's booking page.
- Tests for the booking rules, double bookings, validation and the booking pages.

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
