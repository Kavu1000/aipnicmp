"""An account that belongs to one network and may see only that network.

The four Lao operators compete, so this is not a convenience filter. The scope
lives on the account and is applied server-side on every request; a client that
asks for somebody else's network is refused rather than quietly corrected.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("scoped_operator", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("role_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("role_changed_by", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "role_changed_by")
    op.drop_column("users", "role_changed_at")
    op.drop_column("users", "scoped_operator")
