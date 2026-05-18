from app.core.schemas import (
    PriorityEntityMapping,
    PriorityMappingConfig,
)
from app.integrations.erp.priority_mapping import validate_priority_mapping_config


def _mapping() -> PriorityMappingConfig:
    return PriorityMappingConfig(
        vendors=PriorityEntityMapping(
            entity_name="SUPPLIERS",
            external_id_field="SUPNAME",
            fields={"name": "SUPDES", "tax_id": "VATNUM"},
        ),
        purchase_orders=PriorityEntityMapping(
            entity_name="PORDERS",
            external_id_field="ORDNAME",
            fields={
                "po_number": "ORDNAME",
                "vendor_external_id": "SUPNAME",
                "status": "ORDSTATUSDES",
                "total_amount": "TOTPRICE",
                "currency": "CODE",
            },
        ),
        invoice_export=PriorityEntityMapping(
            entity_name="APINVOICES",
            external_id_field="IVNUM",
            fields={
                "invoice_number": "IVNUM",
                "invoice_date": "IVDATE",
                "vendor_external_id": "SUPNAME",
                "total_amount": "TOTPRICE",
                "currency": "CODE",
            },
        ),
    )


def test_priority_mapping_validates_structural_config():
    result = validate_priority_mapping_config(_mapping())

    assert result.status == "partial"
    assert result.errors == []
    assert result.summary["configured_sections"] == [
        "vendors",
        "purchase_orders",
        "invoice_export",
    ]
    assert "validated structurally only" in result.warnings[-1]


def test_priority_mapping_rejects_missing_vendor_required_fields():
    mapping = _mapping().model_copy(
        update={
            "vendors": PriorityEntityMapping(
                entity_name="SUPPLIERS",
                external_id_field="SUPNAME",
                fields={"tax_id": "VATNUM"},
            )
        }
    )

    result = validate_priority_mapping_config(mapping)

    assert result.status == "invalid"
    assert any(
        "vendors.fields is missing required mappings: name" in error
        for error in result.errors
    )


def test_priority_mapping_rejects_missing_purchase_order_required_fields():
    mapping = _mapping().model_copy(
        update={
            "purchase_orders": PriorityEntityMapping(
                entity_name="PORDERS",
                external_id_field="ORDNAME",
                fields={"po_number": "ORDNAME"},
            )
        }
    )

    result = validate_priority_mapping_config(mapping)

    assert result.status == "invalid"
    assert any("vendor_external_id" in error for error in result.errors)


def test_priority_mapping_rejects_missing_invoice_export_required_fields():
    mapping = _mapping().model_copy(
        update={
            "invoice_export": PriorityEntityMapping(
                entity_name="APINVOICES",
                external_id_field="IVNUM",
                fields={"invoice_number": "IVNUM"},
            )
        }
    )

    result = validate_priority_mapping_config(mapping)

    assert result.status == "invalid"
    assert any("invoice_date" in error for error in result.errors)


def test_priority_mapping_rejects_unknown_fields():
    mapping = _mapping().model_copy(
        update={
            "vendors": PriorityEntityMapping(
                entity_name="SUPPLIERS",
                external_id_field="SUPNAME",
                fields={"name": "SUPDES", "unsupported": "FIELD"},
            )
        }
    )

    result = validate_priority_mapping_config(mapping)

    assert result.status == "invalid"
    assert any("unknown APFlow fields" in error for error in result.errors)


def test_priority_mapping_validates_against_metadata():
    result = validate_priority_mapping_config(
        _mapping(),
        available_entities={
            "SUPPLIERS": {"SUPNAME", "SUPDES", "VATNUM"},
            "PORDERS": {"ORDNAME", "SUPNAME", "ORDSTATUSDES", "TOTPRICE", "CODE"},
            "APINVOICES": {"IVNUM", "IVDATE", "SUPNAME", "TOTPRICE", "CODE"},
        },
    )

    assert result.status == "valid"
    assert result.errors == []
    assert result.warnings == []


def test_priority_mapping_metadata_reports_missing_fields():
    result = validate_priority_mapping_config(
        _mapping(),
        available_entities={
            "SUPPLIERS": {"SUPNAME", "SUPDES"},
            "PORDERS": {"ORDNAME", "SUPNAME", "ORDSTATUSDES", "TOTPRICE", "CODE"},
            "APINVOICES": {"IVNUM", "IVDATE", "SUPNAME", "TOTPRICE", "CODE"},
        },
    )

    assert result.status == "invalid"
    assert any("VATNUM" in error for error in result.errors)
