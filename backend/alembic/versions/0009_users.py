"""Accounts, roles, and approval before access

Identity comes from Google; authorisation does not. A new account lands in
`pending` and can read nothing until a super admin approves it, so signing in
proves who someone is and no more.

No password column exists, or could: this table holds what Google asserts about
an account and what a super admin decided about it.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Google's stable subject. The address can change; this does not.
        sa.Column("google_sub", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(160)),
        sa.Column("picture_url", sa.String(500)),
        sa.Column("role", sa.String(16), nullable=False, server_default="admin"),
        # Deliberately defaults to pending: a row created by any path that
        # forgets to set this is locked out rather than let in.
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        # An email rather than a foreign key: this is an audit trail, and it
        # should outlive the account that made the decision.
        sa.Column("decided_by", sa.String(320)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_index("ix_users_google_sub", "users", ["google_sub"])
    op.create_index("ix_users_email", "users", ["email"])
    # The super admin's queue: pending first, and role for the members list.
    op.create_index("ix_users_status_role", "users", ["status", "role"])


def downgrade() -> None:
    op.drop_index("ix_users_status_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    op.drop_table("users")
