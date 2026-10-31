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

## Project layout

- `backend/`: Flask app, models, migrations and tests. See [backend/README.md](backend/README.md).
- `frontend/`: Jinja templates and static files. See [frontend/README.md](frontend/README.md).

## Versions

Each build phase is released as a version (`v0.1.0` for phase 1, and so on) and tagged in git. See [CHANGELOG.md](CHANGELOG.md).

## Status

Phase 4 (booking) is done: guests book a service, barber and free time on the shop's page, with no double bookings. Next is phase 5 (management).
