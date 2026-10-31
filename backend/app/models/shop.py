from datetime import datetime, time

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from ..timeutils import utcnow


class DepositMode:
    NONE = "none"
    REQUIRED = "required"
    ALL = (NONE, REQUIRED)


class Shop(db.Model):
    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint(f"deposit_mode IN {DepositMode.ALL}", name="ck_shops_deposit_mode"),
        CheckConstraint("deposit_cents >= 0", name="ck_shops_deposit_cents"),
        CheckConstraint("slot_minutes > 0", name="ck_shops_slot_minutes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Used in the public booking URL: /s/<slug>
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Bucharest")
    deposit_mode: Mapped[str] = mapped_column(String(20), default=DepositMode.NONE)
    deposit_cents: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RON")
    # Booking start times are offered on this grid, e.g. every 15 minutes.
    slot_minutes: Mapped[int] = mapped_column(default=15)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    owner: Mapped["User"] = relationship(back_populates="owned_shops")  # noqa: F821
    members: Mapped[list["ShopMember"]] = relationship(back_populates="shop")
    services: Mapped[list["Service"]] = relationship(back_populates="shop")
    invites: Mapped[list["Invite"]] = relationship(back_populates="shop")

    @property
    def requires_deposit(self) -> bool:
        return self.deposit_mode == DepositMode.REQUIRED


class ShopMember(db.Model):
    """A barber working at a shop. A barber can work at several shops,
    and an owner who also cuts hair has a membership in their own shop."""

    __tablename__ = "shop_members"
    __table_args__ = (UniqueConstraint("shop_id", "user_id", name="uq_shop_members_shop_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(default=True)
    joined_at: Mapped[datetime] = mapped_column(default=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")  # noqa: F821
    working_hours: Mapped[list["WorkingHours"]] = relationship(back_populates="member")
    time_off: Mapped[list["TimeOff"]] = relationship(back_populates="member")


class Invite(db.Model):
    """Single-use, expiring link an owner sends to a barber to join a shop."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    used_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="invites")

    def is_usable(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at


class Service(db.Model):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("duration_min > 0", name="ck_services_duration_min"),
        CheckConstraint("price_cents >= 0", name="ck_services_price_cents"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    duration_min: Mapped[int]
    price_cents: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)

    shop: Mapped[Shop] = relationship(back_populates="services")


class WorkingHours(db.Model):
    """Weekly recurring hours in the shop's local time. Several rows per weekday
    are allowed, which is how breaks are represented (e.g. 09-13 and 14-18).

    A shift that runs until midnight is stored with end_time END_OF_DAY, because
    00:00 would be earlier than its start. Shifts never cross midnight; hours after
    midnight belong to the next weekday's row."""

    END_OF_DAY = time.max  # 23:59:59.999999, shown and entered as 00:00

    __tablename__ = "working_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_working_hours_weekday"),
        CheckConstraint("start_time < end_time", name="ck_working_hours_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("shop_members.id"), index=True)
    # 0 = Monday ... 6 = Sunday, matching datetime.weekday()
    weekday: Mapped[int]
    start_time: Mapped[time]
    end_time: Mapped[time]

    member: Mapped[ShopMember] = relationship(back_populates="working_hours")


class TimeOff(db.Model):
    __tablename__ = "time_off"
    __table_args__ = (CheckConstraint("start_at < end_at", name="ck_time_off_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("shop_members.id"), index=True)
    start_at: Mapped[datetime]  # UTC
    end_at: Mapped[datetime]  # UTC
    reason: Mapped[str | None] = mapped_column(String(255))

    member: Mapped[ShopMember] = relationship(back_populates="time_off")
