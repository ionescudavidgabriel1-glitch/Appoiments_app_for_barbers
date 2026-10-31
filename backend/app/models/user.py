from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, login_manager
from ..timeutils import utcnow


class Role:
    OWNER = "owner"
    BARBER = "barber"
    ALL = (OWNER, BARBER)


class User(UserMixin, db.Model):
    """A person who logs in: a shop owner or a barber. Customers never have accounts."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"role IN {Role.ALL}", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    owned_shops: Mapped[list["Shop"]] = relationship(back_populates="owner")  # noqa: F821
    memberships: Mapped[list["ShopMember"]] = relationship(back_populates="user")  # noqa: F821

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))
