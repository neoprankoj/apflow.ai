from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.schemas import (
    CanonicalInvoice,
    PriorityEntityMapping,
    PriorityMappingConfig,
    PriorityMappingValidationResult,
)

PRIORITY_MAPPING_CONFIG_KEY = "priority_mapping"

_ALLOWED_FIELDS = {
    "vendors": {"name", "tax_id", "email", "payment_terms"},
    "purchase_orders": {
        "po_number",
        "vendor_external_id",
        "vendor_name",
        "vendor_tax_id",
        "status",
        "total_amount",
        "currency",
    },
    "invoice_export": {
        "invoice_number",
        "invoice_date",
        "vendor_external_id",
        "total_amount",
        "currency",
        "description",
    },
}

_REQUIRED_FIELDS = {
    "vendors": {"name"},
    "purchase_orders": {"po_number", "vendor_external_id"},
    "invoice_export": {
        "invoice_number",
        "invoice_date",
        "vendor_external_id",
        "total_amount",
        "currency",
    },
}

_RECOMMENDED_FIELDS = {
    "purchase_orders": {"status", "total_amount", "currency"},
}


def priority_mapping_from_config(config: dict[str, Any] | None) -> PriorityMappingConfig | None:
    raw_mapping = (config or {}).get(PRIORITY_MAPPING_CONFIG_KEY)
    if not raw_mapping:
        return None
    return PriorityMappingConfig.model_validate(raw_mapping)


def config_with_priority_mapping(
    config: dict[str, Any] | None,
    mapping: PriorityMappingConfig,
) -> dict[str, Any]:
    updated = dict(config or {})
    normalized = mapping.model_copy(update={"updated_at": datetime.now(UTC)})
    updated[PRIORITY_MAPPING_CONFIG_KEY] = normalized.model_dump(mode="json")
    return updated


def validate_priority_mapping_config(
    mapping: PriorityMappingConfig | None,
    available_entities: dict[str, set[str]] | None = None,
) -> PriorityMappingValidationResult:
    if mapping is None:
        return PriorityMappingValidationResult(
            status="mapping_required",
            errors=["Priority mapping configuration is required."],
            warnings=[],
            summary={"configured_sections": []},
        )

    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "configured_sections": [],
        "version": mapping.version,
        "metadata_checked": available_entities is not None,
    }

    for section_name in ("vendors", "purchase_orders", "invoice_export"):
        entity_mapping = getattr(mapping, section_name)
        if entity_mapping is None or not entity_mapping.enabled:
            continue
        summary["configured_sections"].append(section_name)
        _validate_entity_mapping(section_name, entity_mapping, errors, warnings)
        if available_entities is not None:
            _validate_against_metadata(section_name, entity_mapping, available_entities, errors)

    if not summary["configured_sections"]:
        return PriorityMappingValidationResult(
            status="mapping_required",
            errors=["At least one enabled Priority mapping section is required."],
            warnings=warnings,
            summary=summary,
        )

    if available_entities is None:
        warnings.append("Priority metadata was not available; mapping was validated structurally only.")

    status = "invalid" if errors else ("partial" if warnings else "valid")
    return PriorityMappingValidationResult(
        status=status,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def build_priority_invoice_payload(
    invoice: CanonicalInvoice,
    mapping: PriorityEntityMapping,
) -> dict[str, Any]:
    source_values = {
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "vendor_external_id": None,
        "total_amount": invoice.grand_total,
        "currency": invoice.currency,
        "description": f"APFlow invoice {invoice.invoice_number}",
    }
    mapped_fields: dict[str, Any] = {}
    missing_fields: list[str] = []
    warnings: list[str] = []
    for apflow_field, priority_field in mapping.fields.items():
        value = source_values.get(apflow_field)
        if value in (None, ""):
            missing_fields.append(apflow_field)
            continue
        mapped_fields[priority_field] = value
    if "vendor_external_id" in mapping.fields and "vendor_external_id" in missing_fields:
        warnings.append("Vendor external reference is required before Priority invoice export.")
    return {
        "entity_name": mapping.entity_name,
        "mapped_fields": mapped_fields,
        "missing_fields": missing_fields,
        "warnings": warnings,
    }


def _validate_entity_mapping(
    section_name: str,
    mapping: PriorityEntityMapping,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not mapping.entity_name.strip():
        errors.append(f"{section_name}.entity_name is required.")
    if not mapping.external_id_field.strip():
        errors.append(f"{section_name}.external_id_field is required.")

    unknown_fields = sorted(set(mapping.fields) - _ALLOWED_FIELDS[section_name])
    if unknown_fields:
        errors.append(f"{section_name}.fields contains unknown APFlow fields: {', '.join(unknown_fields)}.")

    missing_required = sorted(_REQUIRED_FIELDS[section_name] - set(mapping.fields))
    if missing_required:
        errors.append(f"{section_name}.fields is missing required mappings: {', '.join(missing_required)}.")

    missing_recommended = sorted(_RECOMMENDED_FIELDS.get(section_name, set()) - set(mapping.fields))
    if missing_recommended:
        warnings.append(
            f"{section_name}.fields is missing recommended mappings: {', '.join(missing_recommended)}."
        )

    duplicate_targets = sorted(
        field_name
        for field_name, count in Counter(mapping.fields.values()).items()
        if count > 1
    )
    if duplicate_targets:
        warnings.append(
            f"{section_name}.fields reuses Priority fields: {', '.join(duplicate_targets)}."
        )


def _validate_against_metadata(
    section_name: str,
    mapping: PriorityEntityMapping,
    available_entities: dict[str, set[str]],
    errors: list[str],
) -> None:
    available_fields = available_entities.get(mapping.entity_name)
    if available_fields is None:
        errors.append(f"{section_name}.entity_name '{mapping.entity_name}' was not found in Priority metadata.")
        return
    missing_fields = sorted(
        field_name
        for field_name in {mapping.external_id_field, *mapping.fields.values()}
        if field_name not in available_fields
    )
    if missing_fields:
        errors.append(
            f"{section_name} references fields missing from Priority metadata: {', '.join(missing_fields)}."
        )
