"""Add payment statuses."""

from alembic import op
import sqlalchemy as sa


revision = "0003_payment_statuses"
down_revision = "0002_uploaded_invoice_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_statuses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("amount_due", sa.Numeric(18, 4), nullable=True),
        sa.Column("amount_paid", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("scheduled_payment_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_payment_reference", sa.String(length=255), nullable=True),
        sa.Column("safe_vendor_message", sa.Text(), nullable=True),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_statuses_tenant_id"), "payment_statuses", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_payment_statuses_invoice_id"), "payment_statuses", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_payment_statuses_status"), "payment_statuses", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_statuses_status"), table_name="payment_statuses")
    op.drop_index(op.f("ix_payment_statuses_invoice_id"), table_name="payment_statuses")
    op.drop_index(op.f("ix_payment_statuses_tenant_id"), table_name="payment_statuses")
    op.drop_table("payment_statuses")
