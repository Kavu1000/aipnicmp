"""Who is credited on the sign-in page, and their portrait.

Credit is kept apart from access on purpose. Driving the public credits list
from the role column alone would mean granting somebody admin published their
name and photograph to every visitor, and removing their access erased them
from work they did. So appearing is an explicit act by a super admin, and the
role only decides which heading they appear under.

The image is stored here rather than linked. Google's photo URLs expire, and
linking one would have every visitor's browser fetch it from Google before
they have signed in to anything — telling Google who reads this platform.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "show_in_credits",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # What they did, not what they may do: "Android collector" rather than
    # "admin". Free text because the roles on a student project do not fit a
    # vocabulary anybody has written down.
    op.add_column("users", sa.Column("credit_title", sa.String(120), nullable=True))
    op.add_column("users", sa.Column("avatar_image", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("avatar_content_type", sa.String(40), nullable=True))
    # Partial index: the public endpoint asks only for the credited few, and
    # they will always be a handful against every account ever created.
    op.create_index(
        "ix_users_credited",
        "users",
        ["show_in_credits"],
        postgresql_where=sa.text("show_in_credits"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_credited", table_name="users")
    op.drop_column("users", "avatar_content_type")
    op.drop_column("users", "avatar_image")
    op.drop_column("users", "credit_title")
    op.drop_column("users", "show_in_credits")
