"""Sign up, login and logout for shop owners and barbers.

Owners sign up here. Barbers join through an invite link from an owner (phase 3).
"""

from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from ..extensions import db
from ..forms import LoginForm, LogoutForm, SignupForm
from ..models import Role, User

bp = Blueprint("auth", __name__)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_safe_next(target: str | None) -> bool:
    """Only allow redirects to paths on this site, never to another host."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("shops.dashboard"))

    form = SignupForm()
    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        if db.session.scalar(select(User).where(User.email == email)):
            form.email.errors.append("An account with this email already exists.")
        else:
            user = User(email=email, name=form.name.data.strip(), role=Role.OWNER)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Welcome! Your account is ready.", "success")
            return redirect(url_for("shops.dashboard"))

    return render_template("auth/signup.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("shops.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        user = db.session.scalar(select(User).where(User.email == email))
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_url = request.args.get("next")
            return redirect(next_url if is_safe_next(next_url) else url_for("shops.dashboard"))
        # Same message for unknown email and wrong password, so emails can't be probed.
        flash("Incorrect email or password.", "error")

    return render_template("auth/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    if LogoutForm().validate_on_submit():
        logout_user()
        flash("You have been logged out.", "success")
    return redirect(url_for("main.home"))
