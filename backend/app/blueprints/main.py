from flask import Blueprint, render_template
from sqlalchemy import text

from ..extensions import db

bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    return render_template("main/home.html")


@bp.get("/healthz")
def healthz():
    """For the host's health check: the app runs and the database answers."""
    db.session.execute(text("SELECT 1"))
    return {"status": "ok"}
