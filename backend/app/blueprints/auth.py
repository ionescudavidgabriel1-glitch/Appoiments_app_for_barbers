"""Sign up, login and logout for shop owners and barbers.

Owners sign up at /auth/signup. Barbers join through an invite link from an owner,
which either creates their account or adds a shop to the account they have.
"""

from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from ..extensions import db, limiter
from ..forms import ActionForm, LoginForm, SignupForm
from ..models import Invite, Role, ShopMember, User
from ..security import hash_token
from ..timeutils import utcnow

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
@limiter.limit("10 per hour", methods=["POST"])
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
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
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
    if ActionForm().validate_on_submit():
        logout_user()
        flash("You have been logged out.", "success")
    return redirect(url_for("main.home"))


def usable_invite_or_none(token: str) -> Invite | None:
    invite = db.session.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))
    if invite is None or not invite.is_usable(utcnow()):
        return None
    return invite


def join_shop(user: User, invite: Invite) -> None:
    """Add the user to the invite's shop and use up the invite."""
    if not any(m.shop_id == invite.shop_id for m in user.memberships):
        db.session.add(ShopMember(shop_id=invite.shop_id, user=user, display_name=user.name))
    invite.used_at = utcnow()
    invite.used_by_id = user.id
    db.session.commit()


@bp.route("/invite/<token>", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def accept_invite(token):
    invite = usable_invite_or_none(token)
    if invite is None:
        return render_template("auth/invite_invalid.html"), 404
    shop = invite.shop

    if current_user.is_authenticated:
        form = ActionForm()
        if form.validate_on_submit():
            join_shop(current_user, invite)
            flash(
                f"You joined {shop.name}. Set your working hours so customers can book you.",
                "success",
            )
            return redirect(url_for("shops.dashboard"))
        already_member = any(m.shop_id == shop.id for m in current_user.memberships)
        return render_template(
            "auth/invite_join.html", form=form, shop=shop, already_member=already_member
        )

    form = SignupForm()
    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        if db.session.scalar(select(User).where(User.email == email)):
            form.email.errors.append("An account with this email already exists. Log in to join.")
        else:
            user = User(email=email, name=form.name.data.strip(), role=Role.BARBER)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            join_shop(user, invite)
            login_user(user)
            flash(
                f"Welcome to {shop.name}! Set your working hours so customers can book you.",
                "success",
            )
            return redirect(url_for("shops.dashboard"))
    return render_template("auth/invite_signup.html", form=form, shop=shop, token=token)
