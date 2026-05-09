"""add uploaded invoice document metadata

Revision ID: 0002_uploaded_invoice_documents
Revises: 0001_initial_persistence
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_uploaded_invoice_documents"
down_revision: str | None = "0001_initial_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "uploaded_invoice_documents" in inspector.get_table_names():
        return

    op.create_table(
        "uploaded_invoice_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("uploaded_by", sa.String(length=320), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_uploaded_invoice_documents_tenant_id",
        "uploaded_invoice_documents",
        ["tenant_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "uploaded_invoice_documents" not in inspector.get_table_names():
        return

    op.drop_index("ix_uploaded_invoice_documents_tenant_id", table_name="uploaded_invoice_documents")
    op.drop_table("uploaded_invoice_documents")
