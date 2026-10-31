"""Owner and barber pages for managing a shop (phases 3 and 5)."""

from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint("shops", __name__)


@bp.get("/")
@login_required
def dashboard():
    return render_template("shops/dashboard.html")
