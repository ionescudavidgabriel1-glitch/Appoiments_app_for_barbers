# CLAUDE.md

Guidance for Claude when working in this repository.

## Project

**Appoiments_app_for_barbers** is a web app where customers book appointments at a barbershop, and the shop manages its barbers, services and schedules.

Status: phase 6 (notifications) is done. Next: translating the interface (language switcher), then phase 7 (polish and deploy). Deposits (Stripe) are decided but not yet placed in a phase; bookings are confirmed without payment for now. Follow the design system in `frontend/README.md` for new pages, and use the frontend-design skill for UI work.

## Stack (confirmed)

- Backend: Python with Flask, organized with an app factory and blueprints (auth, booking, admin)
- Database: SQLite in development, PostgreSQL in production, via SQLAlchemy
- Migrations: Flask-Migrate (Alembic)
- Auth: Flask-Login with hashed passwords (Werkzeug); roles for owner and barber (customers have no account)
- Forms and CSRF: Flask-WTF
- Frontend: server-rendered Jinja templates with Tailwind CSS; HTMX only where slot selection needs partial updates
- Booking rules: plain Python in a service module, no scheduling library
- Notifications: SMTP email; APScheduler for reminders later
- Tests: pytest with the Flask test client; Playwright (webapp-testing skill) for page-level checks
- Config: environment variables, loaded with python-dotenv
- Dependencies: virtual environment and requirements.txt
- Lint and format: ruff
- Deployment: Render or Railway, served with gunicorn; PostgreSQL in production

Product decisions (confirmed):
- Several shops. Each shop has a public booking page at `/s/<shop-slug>`.
- Customers book as guests, with no account, and manage a booking through a private link.
- Payments: a shop can optionally require a deposit (Stripe). Unpaid deposit bookings hold their slot for a limited time.
- Guests can cancel or reschedule online any time before the appointment starts.
- Owners manage every booking at their shop; barbers manage only their own.
- Notifications: email only for now (no SMS). Guests get confirmation, change and cancellation emails, and reminders 24 and 2 hours before. Only the barber gets booking alerts, not the owner.
- Language: emails use the shop's language (Romanian or English, from its country/timezone, changeable in settings). Translating the whole interface, with a language switcher, is a separate step after phase 6.

## Build phases

1. Foundation: project structure, config, models (User, Barber, Service, Appointment, Availability), home page
2. Accounts: sign up, login, logout, role-based access
3. Catalog: owners create shops and manage services, barbers (invites) and weekly working hours
4. Booking: pick service, barber and slot; prevent double bookings and past times
5. Management: reschedule and cancel, daily calendar view, time off
6. Notifications: confirmation and reminder emails
7. Polish and deploy: responsive layout, validation, error pages, tests

Work one phase at a time. Finish and test a phase before starting the next.

## Conventions

- Keep code simple and readable. Match the style of the surrounding code.
- After each change, explain to the user in simple words every new file and every addition: what it does and how it fits into the codebase. The user is learning the codebase.
- Write tests for booking logic, especially slot conflicts and time validation.
- Never store secrets in the repo. Load them from environment variables, and keep `.env` out of git.
- Add a `.gitignore` before the first commit that covers `__pycache__/`, `.venv/`, `.env` and local database files.
- Keep the README current when setup or usage changes.

## Documentation layout

Each area has its own README. Keep them current as part of the same change:

- `README.md` (root): what the app is, setup, how to run and test, and links to the area READMEs.
- `backend/README.md`: API endpoints, data models, how to run the server and tests.
- `frontend/README.md`: pages, components, how to run the client.

Rules:
- When you change backend code, update `backend/README.md`.
- When you change frontend code, update `frontend/README.md`.
- When you change setup, commands or project-wide conventions, update the root `README.md`.
- If a change affects both areas, update both READMEs.
- Create an area README when its folder is first created, and keep it short.

## Working in this repo

- The repo is on `main`, tracking `origin` on GitHub (`Appoiments_app_for_barbers`).
- Do not commit or push unless the user asks. Work on a feature branch for larger changes.
- Before destructive git operations (force push, reset, deleting files), confirm with the user.
- Commit messages: short imperative subject, plus a body when the reason isn't obvious.

## Versioning

Each finished build phase is one version:

- Phase N is released as `v0.N.0` (phase 1 = `v0.1.0`). Phase 7 (polish and deploy) is `v1.0.0`.
- Fixes to a released phase bump the patch number, e.g. `v0.1.1`.
- Work on each phase happens on a branch named `phase-N-<name>`, e.g. `phase-2-accounts`.
- When a phase is finished and its tests pass:
  1. Set `version` in `pyproject.toml`.
  2. Add an entry to `CHANGELOG.md`.
  3. Commit, then create an annotated tag: `git tag -a v0.N.0 -m "Phase N: <name>"`.
- Merge the phase branch into `main`, and push the branch or tags only when the user asks.

## Commands

Run these from the repository root with the `.venv` virtual environment active:

- Install dependencies: `pip install -r requirements-dev.txt`
- Apply migrations: `flask db upgrade` (create a new one with `flask db migrate -m "..."`)
- Run the app: `flask run`
- Run tests: `pytest`
- Lint and format: `ruff check .` and `ruff format .`
