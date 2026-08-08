"""Record which signature algorithm each device enrolled with

Android's Keystore cannot hold an Ed25519 key, but it can hold a hardware-backed
ECDSA P-256 key whose private half never leaves the secure element. Real devices
therefore enrol ecdsa_p256, and the server has to know which algorithm to verify
against. Existing rows are ed25519 — the simulator and the test suite.

The public_key column widens because an X.509 SubjectPublicKeyInfo for P-256 is
124 base64 characters, uncomfortably close to the old 128 limit.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "devices",
        "public_key",
        existing_type=sa.String(128),
        type_=sa.String(256),
        existing_nullable=True,
    )
    op.add_column(
        "devices",
        sa.Column(
            "key_algorithm",
            sa.String(16),
            nullable=False,
            server_default="ed25519",
        ),
    )


def downgrade() -> None:
    op.drop_column("devices", "key_algorithm")
    op.alter_column(
        "devices",
        "public_key",
        existing_type=sa.String(256),
        type_=sa.String(128),
        existing_nullable=True,
    )
