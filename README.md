# Appoiments_app_for_barbers

A web app where customers book appointments at a barbershop, and shops manage their barbers, services and schedules.

- Several shops can use the app. Each shop has a public booking page at `/s/<shop-slug>`.
- Customers book as guests, with no account. They manage a booking through a private link.
- Shop owners and barbers log in to manage services, working hours and appointments.
- Shops can optionally require a deposit when booking.

Built with Flask, SQLAlchemy and Jinja templates styled with Tailwind CSS.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Windows (Git Bash):   source .venv/Scripts/activate
# macOS / Linux:        source .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium   # browser for page checks
cp .env.example .env      # then edit values if needed
flask db upgrade          # creates backend/instance/barbershop.db
```

## Run

```bash
flask run
```

Open http://127.0.0.1:5000. The `flask` command picks up `FLASK_APP` from `.flaskenv` and secrets from `.env`.

## Reminder emails

Reminders are sent by a separate process. In a second terminal:

```bash
flask reminders-worker
```

## Test and lint

```bash
pytest
ruff check .
ruff format .
```

## Configuration

Settings come from environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development`, `testing` or `production` |
| `SECRET_KEY` | Session signing key. Required in production. |
| `DATABASE_URL` | Database URL. Defaults to SQLite in `backend/instance/`. |
| `APP_BASE_URL` | Where the app is reachable; used for links in reminder emails. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `MAIL_FROM` | Sending email. Leave `SMTP_HOST` empty in development: emails are saved to `backend/instance/outbox/`. |

## Project layout

- `backend/`: Flask app, models, migrations and tests. See [backend/README.md](backend/README.md).
- `frontend/`: Jinja templates and static files. See [frontend/README.md](frontend/README.md).

## Versions

Each build phase is released as a version (`v0.1.0` for phase 1, and so on) and tagged in git. See [CHANGELOG.md](CHANGELOG.md).

## Status

Phase 6 (notifications) is done: booking, change and cancellation emails to guests and barbers, reminders 24 and 2 hours before, in Romanian or English per shop. Next: translating the interface, then phase 7 (polish and deploy).
