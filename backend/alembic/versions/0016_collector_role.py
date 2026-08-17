"""A collector account, and the phones it owns.

The link lives here rather than as a column on ``devices``. That table says of
itself that it holds nothing identifying a person, and it is the table the
handset writes to on enrolment; putting an account id in it would make every
enrolment record a statement about somebody. A separate table keeps that
promise intact and lets one person own several handsets, which they must — a
reinstall cannot recover its hardware key, so it enrols as a new device, and
this fleet has already done that eleven times for one model.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_devices",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("install_id", sa.String(64), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        # Who said so. A collector account is a window onto somebody's own
        # movements, so the decision to open it needs an author.
        sa.Column("assigned_by", sa.String(320), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["install_id"], ["devices.install_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "install_id"),
    )
    # A handset belongs to one person. Without this two accounts could each be
    # given the same device and each would believe the readings were theirs.
    op.create_index("ix_user_devices_install", "user_devices", ["install_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_devices_install", table_name="user_devices")
    op.drop_table("user_devices")
