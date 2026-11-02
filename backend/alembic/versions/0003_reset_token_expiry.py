"""password reset and invitation token expiry

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("password_resets", sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("password_resets", "expires_at")
