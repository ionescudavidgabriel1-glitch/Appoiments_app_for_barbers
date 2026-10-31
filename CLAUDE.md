# CLAUDE.md

Guidance for Claude when working in this repository.

## Project

**Appoiments_app_for_barbers** is a web app where customers book appointments at a barbershop, and the shop manages its barbers, services and schedules.

Status: early planning. The repo has only the initial README. No stack or structure has been decided yet.

## Planned stack (proposed, not yet confirmed)

- Backend: Python with Flask (Django is the alternative)
- Database: SQLite in development, PostgreSQL in production, via SQLAlchemy
- Frontend: Jinja templates with Tailwind CSS
- Auth: email and password, with roles for customer, barber and admin
- Tests: pytest

Confirm these choices with the user before building on them.

## Build phases

1. Foundation: project structure, config, models (User, Barber, Service, Appointment, Availability), home page
2. Accounts: sign up, login, logout, role-based access
3. Catalog: admin manages services and barbers
4. Booking: pick service, barber and slot; prevent double bookings and past times
5. Management: reschedule and cancel, daily calendar view
6. Notifications: confirmation and reminder emails
7. Polish and deploy: responsive layout, validation, error pages, tests

Work one phase at a time. Finish and test a phase before starting the next.

## Conventions

- Keep code simple and readable. Match the style of the surrounding code.
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

## Commands

Add these once the project is set up:

- Install dependencies: _TBD_
- Run the app: _TBD_
- Run tests: _TBD_
