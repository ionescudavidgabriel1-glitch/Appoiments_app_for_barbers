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
    forms.py         Flask-WTF forms (sign up, login, logout)
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
| `auth` | `/auth` | `GET, POST /signup`, `GET, POST /login`, `POST /logout` |
| `shops` | `/shops` | `GET /` dashboard (login required); management pages in phases 3 and 5 |
| `admin` | `/admin` | empty |
| `booking` | `/s` | empty, phase 4 (public pages at `/s/<shop-slug>`) |

## Accounts and access

- Only shop owners sign up at `/auth/signup`. Barbers will join through an invite link (phase 3). Customers never have accounts.
- Emails are stored in lowercase, so login is case-insensitive.
- Passwords need at least 8 characters and are stored hashed (Werkzeug).
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
