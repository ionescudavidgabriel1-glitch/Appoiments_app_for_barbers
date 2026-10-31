# Backend

Flask app built with an app factory (`app/__init__.py:create_app`) and blueprints. Run every command from the repository root.

## Layout

```
backend/
  wsgi.py            entry point for flask and gunicorn
  app/
    __init__.py      app factory
    config.py        Development, Testing and Production configs
    extensions.py    db, migrate, login_manager, csrf
    forms.py         Flask-WTF forms (accounts, shop, service, working hours)
    catalog.py       shop and service rules: slugs, prices in cents, saving working hours
    booking.py       booking rules: free start times, creating, moving and cancelling bookings
    notifications.py emails about bookings, and reminders
    commands.py      flask send-reminders and flask reminders-worker
    translations/    Romanian catalog for emails (messages.po, compiled to messages.mo)
    decorators.py    role_required: limits a view to certain roles
    security.py      tokens for invite and booking links (stored as SHA-256 hashes)
    timeutils.py     UTC helpers and shop-timezone conversion
    models/          SQLAlchemy models
    blueprints/      main, auth, shops, calendar, admin, booking
  migrations/        Alembic migrations (Flask-Migrate)
  tests/             pytest suite
  instance/          local SQLite database (not in git)
```

## Routes

| Blueprint | Prefix | Status |
| --- | --- | --- |
| `main` | `/` | `GET /` home page |
| `auth` | `/auth` | `GET, POST /signup`, `GET, POST /login`, `POST /logout`, `GET, POST /invite/<token>` |
| `shops` | `/shops` | dashboard and shop management, see below |
| `calendar` | `/shops` | daily calendar, single bookings, time off, see below |
| `admin` | `/admin` | empty |
| `booking` | `/s` | public booking pages, see below |

### Shop management (`/shops`)

All pages need a login. Pages for a shop are owner-only; anyone else gets 404, so they can't tell which shops exist.

| Method | Path | What it does | Who |
| --- | --- | --- | --- |
| GET | `/shops/` | Dashboard: your shops and the shops you work at | any user |
| GET, POST | `/shops/new` | Create a shop | owners |
| GET | `/shops/<slug>/` | Shop overview: services, barbers, open invites | shop owner |
| GET, POST | `/shops/<slug>/settings` | Edit name, booking address, contact, timezone, currency, slot grid | shop owner |
| GET, POST | `/shops/<slug>/services/new` | Add a service | shop owner |
| GET, POST | `/shops/<slug>/services/<id>/edit` | Edit a service | shop owner |
| POST | `/shops/<slug>/services/<id>/toggle` | Hide or show a service | shop owner |
| POST | `/shops/<slug>/invites` | Create a barber invite link | shop owner |
| POST | `/shops/<slug>/invites/<id>/revoke` | Cancel an unused invite | shop owner |
| POST | `/shops/<slug>/barbers/add-me` | Add the owner as a barber | shop owner |
| POST | `/shops/<slug>/barbers/<id>/toggle` | Hide or show a barber | shop owner |
| GET, POST | `/shops/<slug>/barbers/<id>/hours` | Weekly working hours | shop owner, or that barber |

### Calendar and bookings (`/shops/<slug>/...`, blueprint `calendar`)

The shop's owner sees and manages every booking; a barber sees and manages only their own bookings and time off. Anyone else gets 404.

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/shops/<slug>/calendar?day=YYYY-MM-DD` | One day: each barber's hours, time off and bookings (default today) |
| GET | `/shops/<slug>/appointments/<id>` | One booking: customer, contact, actions |
| POST | `/shops/<slug>/appointments/<id>/cancel` | Cancel (frees the time) |
| GET, POST | `/shops/<slug>/appointments/<id>/reschedule` | Move to another time; the owner can pick another barber |
| POST | `/shops/<slug>/appointments/<id>/completed` | Record that it happened |
| POST | `/shops/<slug>/appointments/<id>/no-show` | Record that the customer didn't come |
| GET, POST | `/shops/<slug>/barbers/<id>/time-off` | List and add time off |
| POST | `/shops/<slug>/barbers/<id>/time-off/<time_off_id>/delete` | Remove time off |

### Public booking (`/s`)

No login. Guests never have accounts.

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/s/<slug>/` | Booking page. Choices travel in the query string: `?service=<id>&barber=<id or any>&day=YYYY-MM-DD&start=HH:MM` |
| POST | `/s/<slug>/` | Book: the same choices plus `guest_name`, `guest_email`, `guest_phone` |
| GET | `/s/<slug>/booking/<token>` | The guest's private booking page (`?new=1` right after booking shows the link to keep) |
| POST | `/s/<slug>/booking/<token>/cancel` | The guest cancels |
| GET, POST | `/s/<slug>/booking/<token>/reschedule` | The guest moves the booking to another free time |

## Booking rules (`app/booking.py`)

- A start time is offered when it is on the shop's grid (every `slot_minutes` from midnight), the whole service fits inside one working shift, it is in the future, and it overlaps no blocking appointment or time off.
- Blocking appointments: `confirmed`, and `pending_payment` whose hold hasn't expired. Cancelled ones free the time.
- Customers can book from today up to `BOOKING_DAYS_AHEAD` (30) days ahead, counted in the shop's timezone.
- Times are chosen in the shop's local time and stored in UTC, so daylight saving changes are handled.
- "Any barber" offers every time at least one barber is free, and books the first free barber in name order.
- `create_booking` checks availability again inside the transaction, locking the barber's row on PostgreSQL, so two guests can't book overlapping times. The unique index on (barber, start) is the last line of defense. If the time is gone it raises `SlotTaken`, and the guest is sent back to pick again.
- The manage link's token is stored only as a SHA-256 hash; the link is shown once after booking.
- Deposits are not charged yet: every booking is `confirmed`.
- Cancel and reschedule are allowed until the appointment starts (`can_change`), for guests and the shop alike. Rescheduling keeps the service and runs through the same safe check as booking; the booking's own old time counts as free (`ignore=`).
- Completed and no-show can be recorded once the appointment has started, and corrected later (`can_record_outcome`). Cancelled bookings have no outcome.
- Time off is entered in the shop's local time and stored in UTC. Bookings already inside new time off stay booked; the shop is warned to move or cancel them.

## Catalog rules

- The booking address (slug) is made from the shop name when left empty (`Frizeria Ștefan` becomes `frizeria-stefan`, then `-2`, `-3` if taken). Typed slugs must be unique, 3 to 60 characters, lowercase letters, numbers and single dashes.
- Prices are stored as whole cents (`price_cents`) to avoid rounding errors and shown with the `money` template filter, e.g. `5000 | money("RON")` gives `50.00 RON`.
- Service durations are multiples of 5 minutes, from 5 to 480.
- Services and barbers are hidden, never deleted, because past appointments refer to them.
- Working hours: each weekday has an optional first shift and an optional second shift after a break. Saving replaces all of the barber's rows.
- Shifts never cross midnight. Ending at 00:00 means "until midnight" and is stored as `WorkingHours.END_OF_DAY` (23:59:59.999999), because the database requires start < end; the form shows it as 00:00 again. Hours after midnight go on the next weekday.
- Invites: the raw token is shown to the owner once, right after creation (kept in the session for one page view); only its SHA-256 hash is stored. A link works once and expires after `INVITE_EXPIRY_DAYS` (7). Opening it either creates a barber account or, if logged in, adds the shop to the current account.

## Accounts and access

- Only shop owners sign up at `/auth/signup`. Barbers join through an invite link from an owner. Customers never have accounts.
- Emails are stored in lowercase, so login is case-insensitive.
- Passwords need at least 8 characters and are stored hashed (Werkzeug).
- Form error messages are written as plain directions, e.g. "Use at least 8 characters."
- A failed login shows the same message for an unknown email and a wrong password.
- After login, the `next` URL is followed only if it is a path on this site.
- Logout is a POST with a CSRF token, so other sites can't log users out.
- Protect a view with `@login_required` (any logged-in user) or `@role_required(Role.OWNER)` from `app/decorators.py`. Wrong roles get 403.

## Data models

All datetimes are stored as naive UTC. Weekly working hours are stored in the shop's local time.

| Model | Purpose |
| --- | --- |
| `User` | Someone who logs in, with role `owner` or `barber`. Customers have no account. |
| `Shop` | A barbershop: slug for its booking URL, timezone, slot grid, deposit settings |
| `ShopMember` | A barber working at a shop. One user can work at several shops. |
| `Invite` | Single-use, expiring link that lets a barber join a shop |
| `Service` | Something a shop offers, with duration and price in cents |
| `WorkingHours` | Weekly hours per member. Several rows per day represent breaks. |
| `TimeOff` | One-off unavailability for a member |
| `Appointment` | A guest booking, with status, payment status and a hashed manage-link token |

Database rules:
- Check constraints cover roles, statuses, positive durations and start before end.
- A partial unique index stops two active bookings (`pending_payment` or `confirmed`) from starting at the same time with the same barber. The booking service (phase 4) will reject overlapping times.
- Foreign keys are enforced on SQLite too. They are switched off only while migrations run.

## Emails and reminders (`app/notifications.py`)

| Event | Guest | Barber |
| --- | --- | --- |
| Booked | Confirmation with the private link | New booking |
| Moved (by guest or shop) | New details | New details; the old barber hears if it moved to someone else |
| Cancelled (by guest or shop) | Cancellation, with a link to book again | Cancellation |
| 24 hours before | Reminder | - |
| 2 hours before | Reminder | - |

- A barber is never emailed about a change they made themselves. The owner gets no emails (as an owner).
- Emails are written in the shop's language (`Shop.language`: `ro` or `en`). New shops pick it from the timezone (Bucharest and Chisinau give Romanian), and owners can change it in shop settings.
- Each email has an HTML and a plain-text part, from `frontend/templates/email/booking.html` and `.txt`.
- Sending never raises: a failed email is logged and the booking change still stands.
- Booking links in later emails are rebuilt from `Appointment.manage_nonce` and `SECRET_KEY` (`security.booking_token`). The database still stores only the link's hash. Changing `SECRET_KEY` makes new emails carry links that no longer match existing bookings.

Where emails go (`MAIL_BACKEND`, see `.env.example`):
- `file` (default when `SMTP_HOST` is empty): saved as `.eml` files in `backend/instance/outbox/`. Open one in a mail app such as Outlook or Thunderbird.
- `smtp`: sent through `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, from `MAIL_FROM`.
- `console`: printed in the terminal. `memory`: kept in a list (tests).

Reminders:
- Due when the booking is confirmed, starts within 24 hours (or 2 hours), and was booked before that window began, so a last-minute booking doesn't get a reminder right after its confirmation. If the 2-hour reminder is due, a late 24-hour one is skipped. Moving a booking resets both.
- `flask reminders-worker` keeps running and checks every `REMINDER_CHECK_MINUTES` (5). Run one next to the web server (in production, a separate worker process). `flask send-reminders` checks once, for use from cron.
- Each reminder is claimed with a conditional UPDATE before it is sent, so two workers never send the same one twice.
- Links in reminders start with `APP_BASE_URL`.

## Translations

Emails are translated with Flask-Babel. The interface is still English only. Wrap new text in `_()` and update the catalog:

```bash
pybabel extract -F babel.cfg -k _ -o backend/app/translations/messages.pot .
pybabel update -i backend/app/translations/messages.pot -d backend/app/translations
# translate the new entries in backend/app/translations/ro/LC_MESSAGES/messages.po
pybabel compile -d backend/app/translations
```

Commit both `messages.po` and the compiled `messages.mo`.

## Migrations

```bash
flask db migrate -m "Describe the change"   # after changing models
flask db upgrade
```

Review each generated file in `migrations/versions/` before committing it.

## Tests

```bash
pytest
```

Tests use an in-memory SQLite database (`TestingConfig`) with CSRF disabled. Fixtures live in `tests/conftest.py`.
