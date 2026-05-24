"""Add vendor access lifecycle fields."""

from alembic import op
import sqlalchemy as sa


revision = "0004_vendor_access_lifecycle"
down_revision = "0003_payment_statuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vendor_portal_access", sa.Column("token_prefix", sa.String(length=32), nullable=True))
    op.add_column("vendor_portal_access", sa.Column("label", sa.String(length=255), nullable=True))
    op.add_column("vendor_portal_access", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vendor_portal_access", sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("vendor_portal_access", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("vendor_portal_access", sa.Column("rotated_from_access_id", sa.Uuid(), nullable=True))
    op.add_column("vendor_portal_access", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        op.f("ix_vendor_portal_access_token_prefix"),
        "vendor_portal_access",
        ["token_prefix"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vendor_portal_access_token_prefix"), table_name="vendor_portal_access")
    op.drop_column("vendor_portal_access", "last_used_at")
    op.drop_column("vendor_portal_access", "rotated_from_access_id")
    op.drop_column("vendor_portal_access", "created_by_user_id")
    op.drop_column("vendor_portal_access", "revoked_by_user_id")
    op.drop_column("vendor_portal_access", "revoked_at")
    op.drop_column("vendor_portal_access", "label")
    op.drop_column("vendor_portal_access", "token_prefix")
