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

## Styles

The CSS is prebuilt and committed (`frontend/static/css/tailwind.css`), so running the app needs no Node.js. After changing classes in templates, rebuild it (needs Node.js):

```bash
npm install
npm run build:css      # or: npm run watch:css while editing
```

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

## Deploy (Render)

The repository includes `render.yaml`, a Render Blueprint with two parts on free plans: the website and a PostgreSQL database.

1. Push `main` to GitHub.
2. In Render, choose **New > Blueprint** and pick this repository.
3. Render asks for the values marked `sync: false`:
   - `APP_BASE_URL`: the site's address, e.g. `https://barbershop-web.onrender.com` (you can fill it in after the first deploy shows the address, then redeploy).
   - `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM`: the mail account. Leave them empty to start; emails then go to the log instead of being sent.
4. Apply. Render builds with `pip install -r requirements.txt`, runs `flask db upgrade`, then starts gunicorn. `SECRET_KEY` is generated once.
5. Open the site and sign up as the first shop owner.

Every push to `main` deploys again; migrations run on each deploy. Free plans have limits: the website sleeps after about 15 minutes without visitors (the next visit takes a minute to wake it), and the free database expires after a time set by Render; check Render's current terms.

Reminder emails (24 and 2 hours before) need an always-on process, which Render only offers on paid plans, so the Blueprint leaves it out for now. Booking, change and cancellation emails still work. To turn reminders on later, add a paid Background Worker with the start command `flask reminders-worker`, the `barbershop-shared` env group, `DATABASE_URL` from `barbershop-db` and the same mail settings as the website.

GitHub Actions (`.github/workflows/ci.yml`) runs ruff and the tests on every push, runs migrations and tests on PostgreSQL, and checks that the built CSS is up to date.

## Configuration

Settings come from environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development`, `testing` or `production` |
| `SECRET_KEY` | Session signing key. Required in production. |
| `DATABASE_URL` | Database URL. Defaults to SQLite in `backend/instance/`. |
| `APP_BASE_URL` | Where the app is reachable; used for links in reminder emails. |
| `TRUST_PROXY` | Production only, default on: trust the host's proxy headers (Render). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `MAIL_FROM` | Sending email. Leave `SMTP_HOST` empty in development: emails are saved to `backend/instance/outbox/`. |

## Project layout

- `backend/`: Flask app, models, migrations and tests. See [backend/README.md](backend/README.md).
- `frontend/`: Jinja templates and static files. See [frontend/README.md](frontend/README.md).

## Versions

Each build phase is released as a version (`v0.1.0` for phase 1, and so on) and tagged in git. See [CHANGELOG.md](CHANGELOG.md).

## Status

Version 1.0: all seven phases are done and the app is ready to deploy on Render. Next: translating the interface into Romanian with a language switcher (v1.1).
