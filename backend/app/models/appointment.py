from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from ..timeutils import utcnow


class AppointmentStatus:
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    ALL = (PENDING_PAYMENT, CONFIRMED, CANCELLED, COMPLETED, NO_SHOW)
    # Statuses that occupy the barber's time.
    BLOCKING = (PENDING_PAYMENT, CONFIRMED)


class PaymentStatus:
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    ALL = (NOT_REQUIRED, PENDING, PAID, FAILED, REFUNDED)


_blocking = f"status IN {AppointmentStatus.BLOCKING}"


class Appointment(db.Model):
    """A guest booking. Guests have no account; they manage the booking through
    a private link whose token is stored here only as a hash."""

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(f"status IN {AppointmentStatus.ALL}", name="ck_appointments_status"),
        CheckConstraint(
            f"payment_status IN {PaymentStatus.ALL}", name="ck_appointments_payment_status"
        ),
        CheckConstraint("start_at < end_at", name="ck_appointments_order"),
        CheckConstraint("deposit_cents >= 0", name="ck_appointments_deposit_cents"),
        # Last line of defense against two active bookings starting at the same time
        # for one barber. Overlapping (not identical) times are rejected by the booking
        # service inside a transaction; a PostgreSQL exclusion constraint can be added
        # once production runs on PostgreSQL.
        Index(
            "uq_appointments_member_start_active",
            "member_id",
            "start_at",
            unique=True,
            sqlite_where=text(_blocking),
            postgresql_where=text(_blocking),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("shop_members.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    start_at: Mapped[datetime]  # UTC
    end_at: Mapped[datetime]  # UTC

    guest_name: Mapped[str] = mapped_column(String(120))
    guest_email: Mapped[str] = mapped_column(String(255))
    guest_phone: Mapped[str] = mapped_column(String(40))

    status: Mapped[str] = mapped_column(String(20), default=AppointmentStatus.CONFIRMED)
    manage_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Rebuilds the manage link for later emails, together with SECRET_KEY.
    manage_nonce: Mapped[str | None] = mapped_column(String(32))

    deposit_cents: Mapped[int] = mapped_column(default=0)
    payment_status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.NOT_REQUIRED)
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    # Unpaid deposit bookings release their slot after this time.
    hold_expires_at: Mapped[datetime | None]

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    cancelled_at: Mapped[datetime | None]
    # When each reminder email went out. Reset when the booking moves.
    reminder_24h_sent_at: Mapped[datetime | None]
    reminder_2h_sent_at: Mapped[datetime | None]

    shop: Mapped["Shop"] = relationship()  # noqa: F821
    member: Mapped["ShopMember"] = relationship()  # noqa: F821
    service: Mapped["Service"] = relationship()  # noqa: F821
