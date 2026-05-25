"""Add tenant usage events."""

from alembic import op
import sqlalchemy as sa


revision = "0006_usage_events"
down_revision = "0005_notification_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("related_invoice_id", sa.Uuid(), nullable=True),
        sa.Column("related_document_id", sa.Uuid(), nullable=True),
        sa.Column("related_vendor_access_id", sa.Uuid(), nullable=True),
        sa.Column("related_payment_status_id", sa.Uuid(), nullable=True),
        sa.Column("related_notification_delivery_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["related_invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["related_document_id"], ["uploaded_invoice_documents.id"]),
        sa.ForeignKeyConstraint(["related_vendor_access_id"], ["vendor_portal_access.id"]),
        sa.ForeignKeyConstraint(["related_payment_status_id"], ["payment_statuses.id"]),
        sa.ForeignKeyConstraint(["related_notification_delivery_id"], ["notification_deliveries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usage_events_tenant_id"), "usage_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_usage_events_event_type"), "usage_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_usage_events_source"), "usage_events", ["source"], unique=False)
    op.create_index(op.f("ix_usage_events_related_invoice_id"), "usage_events", ["related_invoice_id"], unique=False)
    op.create_index(op.f("ix_usage_events_related_document_id"), "usage_events", ["related_document_id"], unique=False)
    op.create_index(
        op.f("ix_usage_events_related_vendor_access_id"),
        "usage_events",
        ["related_vendor_access_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usage_events_related_payment_status_id"),
        "usage_events",
        ["related_payment_status_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usage_events_related_notification_delivery_id"),
        "usage_events",
        ["related_notification_delivery_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_events_related_notification_delivery_id"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_related_payment_status_id"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_related_vendor_access_id"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_related_document_id"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_related_invoice_id"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_source"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_event_type"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_tenant_id"), table_name="usage_events")
    op.drop_table("usage_events")
