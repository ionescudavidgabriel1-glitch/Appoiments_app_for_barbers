"""Owner and barber pages for managing a shop.

Every page under /shops/<slug>/ belongs to one shop. Only that shop's owner can
manage it; a barber can only edit their own working hours. Anyone else gets 404,
so the pages don't reveal which shops exist.
"""

from datetime import timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import select

from ..catalog import hours_by_day, save_working_hours, slug_taken, to_cents, unique_slug
from ..decorators import role_required
from ..extensions import db
from ..forms import ServiceForm, ShopForm, WorkingHoursForm
from ..models import Invite, Role, Service, Shop, ShopMember
from ..security import generate_token, hash_token
from ..timeutils import utcnow

bp = Blueprint("shops", __name__)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def owned_shop_or_404(slug: str) -> Shop:
    shop = db.session.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None or shop.owner_id != current_user.id:
        abort(404)
    return shop


def shop_item_or_404(model, item_id: int, shop: Shop):
    item = db.session.get(model, item_id)
    if item is None or item.shop_id != shop.id:
        abort(404)
    return item


@bp.get("/")
@login_required
def dashboard():
    return render_template("shops/dashboard.html")


# Shop


@bp.route("/new", methods=["GET", "POST"])
@role_required(Role.OWNER)
def create_shop():
    form = ShopForm()
    if form.validate_on_submit():
        if form.slug.data and slug_taken(form.slug.data):
            form.slug.errors.append("Another shop already uses this address. Try a different one.")
        else:
            shop = Shop(owner=current_user, slug=form.slug.data or unique_slug(form.name.data))
            fill_shop(shop, form)
            db.session.add(shop)
            db.session.commit()
            flash(f"{shop.name} is open. Add your services and barbers next.", "success")
            return redirect(url_for("shops.overview", slug=shop.slug))
    return render_template("shops/shop_form.html", form=form, shop=None)


@bp.route("/<slug>/settings", methods=["GET", "POST"])
@role_required(Role.OWNER)
def edit_shop(slug):
    shop = owned_shop_or_404(slug)
    form = ShopForm(obj=shop)
    if form.validate_on_submit():
        new_slug = form.slug.data or shop.slug
        if slug_taken(new_slug, exclude_shop_id=shop.id):
            form.slug.errors.append("Another shop already uses this address. Try a different one.")
        else:
            shop.slug = new_slug
            fill_shop(shop, form)
            db.session.commit()
            flash("Shop settings saved.", "success")
            return redirect(url_for("shops.overview", slug=shop.slug))
    return render_template("shops/shop_form.html", form=form, shop=shop)


def fill_shop(shop: Shop, form: ShopForm) -> None:
    shop.name = form.name.data.strip()
    shop.address = form.address.data or None
    shop.phone = form.phone.data or None
    shop.timezone = form.timezone.data
    shop.currency = form.currency.data
    shop.slot_minutes = form.slot_minutes.data


@bp.get("/<slug>/")
@role_required(Role.OWNER)
def overview(slug):
    shop = owned_shop_or_404(slug)
    # Shown once, right after the invite is created. Only the hash is stored.
    new_invite = session.pop("new_invite", None)
    if new_invite and new_invite["shop_id"] != shop.id:
        new_invite = None
    now = utcnow()
    open_invites = [i for i in shop.invites if i.is_usable(now)]
    owner_member = next((m for m in shop.members if m.user_id == current_user.id), None)
    return render_template(
        "shops/overview.html",
        shop=shop,
        services=sorted(shop.services, key=lambda s: (not s.active, s.name.lower())),
        members=sorted(shop.members, key=lambda m: (not m.active, m.display_name.lower())),
        open_invites=sorted(open_invites, key=lambda i: i.expires_at),
        new_invite_link=new_invite["link"] if new_invite else None,
        owner_is_barber=owner_member is not None,
    )


# Services


@bp.route("/<slug>/services/new", methods=["GET", "POST"])
@role_required(Role.OWNER)
def create_service(slug):
    shop = owned_shop_or_404(slug)
    form = ServiceForm()
    if form.validate_on_submit():
        service = Service(shop=shop)
        fill_service(service, form)
        db.session.add(service)
        db.session.commit()
        flash(f"{service.name} added.", "success")
        return redirect(url_for("shops.overview", slug=shop.slug))
    return render_template("shops/service_form.html", form=form, shop=shop, service=None)


@bp.route("/<slug>/services/<int:service_id>/edit", methods=["GET", "POST"])
@role_required(Role.OWNER)
def edit_service(slug, service_id):
    shop = owned_shop_or_404(slug)
    service = shop_item_or_404(Service, service_id, shop)
    form = ServiceForm(obj=service)
    if not form.is_submitted():
        form.price.data = service.price_cents / 100
    if form.validate_on_submit():
        fill_service(service, form)
        db.session.commit()
        flash(f"{service.name} saved.", "success")
        return redirect(url_for("shops.overview", slug=shop.slug))
    return render_template("shops/service_form.html", form=form, shop=shop, service=service)


def fill_service(service: Service, form: ServiceForm) -> None:
    service.name = form.name.data.strip()
    service.duration_min = form.duration_min.data
    service.price_cents = to_cents(form.price.data)


@bp.post("/<slug>/services/<int:service_id>/toggle")
@role_required(Role.OWNER)
def toggle_service(slug, service_id):
    # Services are hidden, not deleted, because past appointments refer to them.
    shop = owned_shop_or_404(slug)
    service = shop_item_or_404(Service, service_id, shop)
    service.active = not service.active
    db.session.commit()
    if service.active:
        flash(f"{service.name} is bookable again.", "success")
    else:
        flash(f"{service.name} is hidden from the booking page.", "info")
    return redirect(url_for("shops.overview", slug=shop.slug))


# Barbers and invites


@bp.post("/<slug>/invites")
@role_required(Role.OWNER)
def create_invite(slug):
    shop = owned_shop_or_404(slug)
    token = generate_token()
    days = current_app.config["INVITE_EXPIRY_DAYS"]
    db.session.add(
        Invite(
            shop=shop,
            created_by_id=current_user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(days=days),
        )
    )
    db.session.commit()
    session["new_invite"] = {
        "shop_id": shop.id,
        "link": url_for("auth.accept_invite", token=token, _external=True),
    }
    return redirect(url_for("shops.overview", slug=shop.slug))


@bp.post("/<slug>/invites/<int:invite_id>/revoke")
@role_required(Role.OWNER)
def revoke_invite(slug, invite_id):
    shop = owned_shop_or_404(slug)
    invite = shop_item_or_404(Invite, invite_id, shop)
    if invite.used_at is None:
        db.session.delete(invite)
        db.session.commit()
        flash("Invite link cancelled. It no longer works.", "info")
    return redirect(url_for("shops.overview", slug=shop.slug))


@bp.post("/<slug>/barbers/add-me")
@role_required(Role.OWNER)
def add_owner_as_barber(slug):
    shop = owned_shop_or_404(slug)
    if not any(m.user_id == current_user.id for m in shop.members):
        member = ShopMember(shop=shop, user=current_user, display_name=current_user.name)
        db.session.add(member)
        db.session.commit()
        flash("You're on the team. Set your working hours so customers can book you.", "success")
        return redirect(url_for("shops.edit_hours", slug=shop.slug, member_id=member.id))
    return redirect(url_for("shops.overview", slug=shop.slug))


@bp.post("/<slug>/barbers/<int:member_id>/toggle")
@role_required(Role.OWNER)
def toggle_member(slug, member_id):
    shop = owned_shop_or_404(slug)
    member = shop_item_or_404(ShopMember, member_id, shop)
    member.active = not member.active
    db.session.commit()
    if member.active:
        flash(f"{member.display_name} can be booked again.", "success")
    else:
        flash(f"{member.display_name} is hidden from the booking page.", "info")
    return redirect(url_for("shops.overview", slug=shop.slug))


@bp.route("/<slug>/barbers/<int:member_id>/hours", methods=["GET", "POST"])
@login_required
def edit_hours(slug, member_id):
    shop = db.session.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None:
        abort(404)
    member = shop_item_or_404(ShopMember, member_id, shop)
    is_owner = shop.owner_id == current_user.id
    if not (is_owner or member.user_id == current_user.id):
        abort(404)

    form = WorkingHoursForm()
    if not form.is_submitted():
        for day_form, intervals in zip(form.days, hours_by_day(member), strict=True):
            for n, (start, end) in enumerate(intervals[:2], start=1):
                day_form[f"start{n}"].data = start
                day_form[f"end{n}"].data = end

    if form.validate_on_submit():
        save_working_hours(member, [day.form.intervals() for day in form.days])
        db.session.commit()
        flash(f"Working hours saved for {member.display_name}.", "success")
        if is_owner:
            return redirect(url_for("shops.overview", slug=shop.slug))
        return redirect(url_for("shops.dashboard"))

    return render_template(
        "shops/hours.html",
        form=form,
        shop=shop,
        member=member,
        is_owner=is_owner,
        days=list(zip(WEEKDAYS, form.days, strict=True)),
    )
