from uuid import uuid4

import pytest

from app.core.schemas import (
    DuplicateDetectionInput,
    DuplicateStatus,
    InvoiceExtractionInput,
    InvoiceIngestionInput,
    InvoiceIngestionMetadata,
    InvoiceNormalizationInput,
    InvoiceSource,
    InvoiceValidationInput,
    InvoiceValidationStatus,
    SupplierIdentityInput,
    SupplierMatchStatus,
)


def _ingestion_input(tenant_id, content: str | None = None) -> InvoiceIngestionInput:
    return InvoiceIngestionInput(
        tenant_id=tenant_id,
        source=InvoiceSource.UPLOAD,
        file_url="mock://incoming/invoice.pdf",
        metadata=InvoiceIngestionMetadata(
            sender_email="ap@example.com",
            original_filename="invoice.pdf",
            mime_type="application/pdf",
        ),
        content=content
        or (
            "invoice_number=INV-100 supplier_name=Northstar Components "
            "supplier_tax_id=TAX-12345 subtotal=1000 tax_total=170 grand_total=1170 "
            "currency=USD invoice_date=2026-05-05"
        ),
    )


def _run_pipeline_once(
    tenant_id,
    repository,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
    invoice_validation_agent,
    duplicate_detection_agent,
):
    repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-12345")
    raw = invoice_ingestion_agent.ingest(_ingestion_input(tenant_id))
    extraction = invoice_extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=raw.tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
        )
    )
    normalized = invoice_normalization_agent.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=raw.tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
            confidence=extraction.confidence,
            file_checksum=raw.file_checksum,
        )
    )
    supplier = supplier_identity_agent.match_supplier(
        SupplierIdentityInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            supplier_name=normalized.canonical_invoice.supplier_name,
            supplier_tax_id=normalized.canonical_invoice.supplier_tax_id,
        )
    )
    validation = invoice_validation_agent.validate(
        InvoiceValidationInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            canonical_invoice=normalized.canonical_invoice,
            vendor_id=supplier.vendor_id,
        )
    )
    duplicate = duplicate_detection_agent.detect(
        DuplicateDetectionInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_number=normalized.canonical_invoice.invoice_number,
            invoice_date=normalized.canonical_invoice.invoice_date,
            grand_total=normalized.canonical_invoice.grand_total,
            file_checksum=normalized.file_checksum,
        )
    )
    return raw, extraction, normalized, supplier, validation, duplicate


def test_invoice_ingestion_stores_tenant_scoped_raw_invoice(
    tenant_id,
    repository,
    invoice_ingestion_agent,
):
    output = invoice_ingestion_agent.ingest(_ingestion_input(tenant_id))

    assert output.status == "stored"
    assert output.file_checksum
    assert repository.get_raw_invoice(tenant_id, output.raw_invoice_id).output == output


def test_invoice_ingestion_rejects_unsupported_files(tenant_id, invoice_ingestion_agent):
    payload = _ingestion_input(tenant_id)
    payload.metadata.mime_type = "application/octet-stream"

    with pytest.raises(ValueError):
        invoice_ingestion_agent.ingest(payload)


def test_extraction_and_normalization_create_canonical_invoice(
    tenant_id,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
):
    raw = invoice_ingestion_agent.ingest(_ingestion_input(tenant_id))
    extraction = invoice_extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
        )
    )
    normalized = invoice_normalization_agent.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
            file_checksum=raw.file_checksum,
        )
    )

    assert extraction.needs_review is False
    assert normalized.canonical_invoice.invoice_number == "INV-100"
    assert normalized.canonical_invoice.grand_total == 1170


def test_supplier_identity_matches_vendor_by_tax_id(
    tenant_id,
    repository,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
):
    repository.add_vendor(tenant_id=tenant_id, name="Different Legal Name", tax_id="TAX-12345")
    raw = invoice_ingestion_agent.ingest(_ingestion_input(tenant_id))
    extraction = invoice_extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
        )
    )
    normalized = invoice_normalization_agent.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
        )
    )

    output = supplier_identity_agent.match_supplier(
        SupplierIdentityInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            supplier_name=normalized.canonical_invoice.supplier_name,
            supplier_tax_id=normalized.canonical_invoice.supplier_tax_id,
        )
    )

    assert output.status == SupplierMatchStatus.MATCHED
    assert output.match_confidence == 1.0


def test_validation_fails_bad_math(tenant_id, invoice_validation_agent):
    from app.core.schemas import CanonicalInvoice

    output = invoice_validation_agent.validate(
        InvoiceValidationInput(
            tenant_id=tenant_id,
            invoice_id=uuid4(),
            canonical_invoice=CanonicalInvoice(
                invoice_number="INV-BAD",
                supplier_name="Vendor",
                invoice_date="2026-05-05",
                currency="USD",
                subtotal=100,
                tax_total=20,
                grand_total=140,
            ),
            vendor_id=uuid4(),
        )
    )

    assert output.validation_status == InvoiceValidationStatus.FAILED
    assert "does not equal" in output.errors[0]


def test_full_core_pipeline_scores_second_identical_invoice_as_duplicate(
    tenant_id,
    repository,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
    invoice_validation_agent,
    duplicate_detection_agent,
):
    first = _run_pipeline_once(
        tenant_id,
        repository,
        invoice_ingestion_agent,
        invoice_extraction_agent,
        invoice_normalization_agent,
        supplier_identity_agent,
        invoice_validation_agent,
        duplicate_detection_agent,
    )
    second = _run_pipeline_once(
        tenant_id,
        repository,
        invoice_ingestion_agent,
        invoice_extraction_agent,
        invoice_normalization_agent,
        supplier_identity_agent,
        invoice_validation_agent,
        duplicate_detection_agent,
    )

    assert first[3].status == SupplierMatchStatus.MATCHED
    assert first[4].validation_status == InvoiceValidationStatus.PASSED
    assert first[5].status == DuplicateStatus.CLEAR
    assert second[5].status == DuplicateStatus.LIKELY_DUPLICATE
    assert second[5].duplicate_score == 1.0
