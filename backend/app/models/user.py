"""People who may see the platform.

Identity comes from Google; authorisation does not. Signing in with Google
proves only that an address belongs to whoever is holding it, which is the
easy half. The half that matters is that a super admin has since looked at the
request and allowed it — so a new account lands in ``pending`` and can read
nothing until then.

That ordering is deliberate. An allowlist checked at sign-in would be the same
idea with the decision made in a config file instead of in the product, and
whoever needed access would have to wait for a redeploy.

No password is ever stored, or could be: this table holds what Google asserts
about an account and what a super admin decided about it, and nothing else.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, timestamp_column

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLES = (ROLE_SUPER_ADMIN, ROLE_ADMIN)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)


class User(Base):
    """One Google account, and what it is allowed to do here."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Google's stable identifier for the account. The address can change —
    # people rename mailboxes, and organisations reassign them — so the subject
    # is what identity is keyed on, and the address is treated as a label.
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(160))
    picture_url: Mapped[str | None] = mapped_column(String(500))

    role: Mapped[str] = mapped_column(String(16), default=ROLE_ADMIN, server_default=ROLE_ADMIN)
    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_PENDING, server_default=STATUS_PENDING
    )

    requested_at: Mapped[datetime] = timestamp_column(server_default=func.now())
    decided_at: Mapped[datetime | None] = timestamp_column()
    # The email of the super admin who decided, kept rather than a foreign key:
    # this is an audit trail, and it should survive that account being removed.
    decided_by: Mapped[str | None] = mapped_column(String(320))

    last_login_at: Mapped[datetime | None] = timestamp_column()
    login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (Index("ix_users_status_role", "status", "role"),)

    @property
    def is_approved(self) -> bool:
        return self.status == STATUS_APPROVED

    @property
    def is_super_admin(self) -> bool:
        return self.role == ROLE_SUPER_ADMIN and self.is_approved

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "picture_url": self.picture_url,
            "role": self.role,
            "status": self.status,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by": self.decided_by,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "login_count": self.login_count,
        }
