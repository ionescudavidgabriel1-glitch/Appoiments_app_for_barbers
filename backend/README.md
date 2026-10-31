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
    decorators.py    role_required: limits a view to certain roles
    security.py      tokens for invite and booking links (stored as SHA-256 hashes)
    timeutils.py     UTC helpers and shop-timezone conversion
    models/          SQLAlchemy models
    blueprints/      main, auth, shops, admin, booking
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
| `admin` | `/admin` | empty |
| `booking` | `/s` | empty, phase 4 (public pages at `/s/<shop-slug>`) |

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

## Catalog rules

- The booking address (slug) is made from the shop name when left empty (`Frizeria Ștefan` becomes `frizeria-stefan`, then `-2`, `-3` if taken). Typed slugs must be unique, 3 to 60 characters, lowercase letters, numbers and single dashes.
- Prices are stored as whole cents (`price_cents`) to avoid rounding errors and shown with the `money` template filter, e.g. `5000 | money("RON")` gives `50.00 RON`.
- Service durations are multiples of 5 minutes, from 5 to 480.
- Services and barbers are hidden, never deleted, because past appointments refer to them.
- Working hours: each weekday has an optional first shift and an optional second shift after a break. Saving replaces all of the barber's rows.
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
