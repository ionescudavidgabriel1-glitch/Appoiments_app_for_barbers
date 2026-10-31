"""Command-line tasks: `flask send-reminders` and `flask reminders-worker`.

Reminders run outside web requests. Run exactly one reminders worker (a separate
process next to the web server), or call send-reminders from a scheduler such as
cron. Running two by mistake is safe: each reminder is claimed before sending.
"""

from datetime import UTC, datetime

import click
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask

from .notifications import send_due_reminders
from .timeutils import utcnow


def run_reminders(app: Flask) -> int:
    # Links in emails need a host; outside a request it comes from APP_BASE_URL.
    with app.app_context(), app.test_request_context(base_url=app.config["APP_BASE_URL"]):
        return send_due_reminders(utcnow())


def register_commands(app: Flask) -> None:
    @app.cli.command("send-reminders")
    def send_reminders():
        """Send the reminder emails that are due now, once."""
        count = run_reminders(app)
        click.echo(f"Sent {count} reminder{'s' if count != 1 else ''}.")

    @app.cli.command("reminders-worker")
    def reminders_worker():
        """Keep running and send due reminders every few minutes."""
        minutes = app.config["REMINDER_CHECK_MINUTES"]
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            lambda: run_reminders(app),
            "interval",
            minutes=minutes,
            next_run_time=datetime.now(UTC),  # first check right away
            max_instances=1,
            coalesce=True,
        )
        click.echo(f"Checking for reminders every {minutes} minutes. Press Ctrl+C to stop.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            pass
