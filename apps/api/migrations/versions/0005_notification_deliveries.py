"""Add notification delivery history."""

from alembic import op
import sqlalchemy as sa


revision = "0005_notification_deliveries"
down_revision = "0004_vendor_access_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("recipient_type", sa.String(length=64), nullable=False),
        sa.Column("recipient_label", sa.String(length=255), nullable=False),
        sa.Column("recipient_address_redacted", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("related_invoice_id", sa.Uuid(), nullable=True),
        sa.Column("related_payment_status_id", sa.Uuid(), nullable=True),
        sa.Column("related_vendor_access_id", sa.Uuid(), nullable=True),
        sa.Column("delivery_metadata", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["related_invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["related_payment_status_id"], ["payment_statuses.id"]),
        sa.ForeignKeyConstraint(["related_vendor_access_id"], ["vendor_portal_access.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_deliveries_tenant_id"), "notification_deliveries", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_notification_deliveries_event_type"), "notification_deliveries", ["event_type"], unique=False)
    op.create_index(op.f("ix_notification_deliveries_channel"), "notification_deliveries", ["channel"], unique=False)
    op.create_index(op.f("ix_notification_deliveries_status"), "notification_deliveries", ["status"], unique=False)
    op.create_index(
        op.f("ix_notification_deliveries_related_invoice_id"),
        "notification_deliveries",
        ["related_invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_deliveries_related_payment_status_id"),
        "notification_deliveries",
        ["related_payment_status_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_deliveries_related_vendor_access_id"),
        "notification_deliveries",
        ["related_vendor_access_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_deliveries_related_vendor_access_id"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_related_payment_status_id"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_related_invoice_id"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_status"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_channel"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_event_type"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_tenant_id"), table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
