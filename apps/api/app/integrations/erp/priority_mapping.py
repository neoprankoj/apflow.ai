from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.schemas import (
    CanonicalInvoice,
    PriorityEntityMapping,
    PriorityMappingConfig,
    PriorityMappingValidationResult,
    PrioritySyncPreviewResponse,
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

_PREVIEW_SECTIONS = {
    "vendors": "vendors",
    "purchase_orders": "purchase_orders",
}

_SAMPLE_PRIORITY_RECORDS: dict[str, list[dict[str, Any]]] = {
    "vendors": [
        {
            "SUPNAME": "SUP-1001",
            "SUPDES": "Demo Office Supplies Ltd.",
            "VATNUM": "DEMO-TAX-999999999",
            "EMAIL": "ap@demo-supplier.local",
            "PAYCODE": "NET30",
        },
        {
            "SUPNAME": "SUP-1002",
            "SUPDES": "Demo Facilities Services Ltd.",
            "VATNUM": "DEMO-TAX-888888888",
            "EMAIL": "billing@demo-facilities.local",
            "PAYCODE": "NET45",
        },
    ],
    "purchase_orders": [
        {
            "ORDNAME": "PO-240001",
            "SUPNAME": "SUP-1001",
            "ORDSTATUSDES": "Open",
            "TOTPRICE": 1170.00,
            "CODE": "USD",
        },
        {
            "ORDNAME": "PO-240002",
            "SUPNAME": "SUP-1002",
            "ORDSTATUSDES": "Approved",
            "TOTPRICE": 2450.50,
            "CODE": "USD",
        },
    ],
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


def priority_sample_records(kind: str, limit: int) -> list[dict[str, Any]]:
    normalized_kind = _normalize_preview_kind(kind)
    return [dict(row) for row in _SAMPLE_PRIORITY_RECORDS[normalized_kind][:limit]]


def build_priority_sync_preview(
    *,
    kind: str,
    mode: str,
    source: str,
    mapping_config: PriorityMappingConfig | None,
    raw_records: list[dict[str, Any]],
    limit: int,
) -> PrioritySyncPreviewResponse:
    normalized_kind = _normalize_preview_kind(kind)
    mapping = getattr(mapping_config, normalized_kind, None) if mapping_config is not None else None
    if mapping is None or not mapping.enabled:
        return PrioritySyncPreviewResponse(
            status="mapping_required",
            kind=normalized_kind,
            mode=mode,
            source=source,
            mapping_status="mapping_required",
            errors=[f"Priority {normalized_kind.replace('_', ' ')} mapping is not configured."],
            warnings=[],
            message="Save a Priority mapping before running a sync preview.",
        )

    validation = validate_priority_mapping_config(_preview_validation_config(kind, mapping_config, mapping))
    if validation.status == "invalid":
        return PrioritySyncPreviewResponse(
            status="invalid_mapping",
            kind=normalized_kind,
            mode=mode,
            source=source,
            mapping_status=validation.status,
            errors=validation.errors,
            warnings=validation.warnings,
            message="Priority mapping must be fixed before running a sync preview.",
        )

    limited_records = [dict(row) for row in raw_records[:limit]]
    mapped_records: list[dict[str, Any]] = []
    warnings = list(validation.warnings)
    for index, raw_record in enumerate(limited_records, start=1):
        mapped, row_warnings = _map_preview_record(normalized_kind, raw_record, mapping, index)
        mapped_records.append(mapped)
        warnings.extend(row_warnings)

    return PrioritySyncPreviewResponse(
        status="preview_ready",
        kind=normalized_kind,
        mode=mode,
        source=source,
        mapping_status=validation.status,
        records_previewed=len(mapped_records),
        raw_records=limited_records,
        mapped_records=mapped_records,
        errors=validation.errors,
        warnings=warnings,
        message=f"Preview generated from {source} records. No data was imported.",
    )


def map_priority_vendor_record(
    raw_record: dict[str, Any],
    mapping: PriorityEntityMapping,
) -> tuple[dict[str, Any], list[str]]:
    return _map_preview_record("vendors", raw_record, mapping, 1)


def map_priority_purchase_order_record(
    raw_record: dict[str, Any],
    mapping: PriorityEntityMapping,
) -> tuple[dict[str, Any], list[str]]:
    return _map_preview_record("purchase_orders", raw_record, mapping, 1)


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


def _normalize_preview_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized in {"vendor", "vendors"}:
        return "vendors"
    if normalized in {"purchase_order", "purchase_orders", "po", "pos"}:
        return "purchase_orders"
    raise ValueError("Priority sync preview kind must be vendors or purchase_orders.")


def _preview_validation_config(
    kind: str,
    mapping_config: PriorityMappingConfig,
    mapping: PriorityEntityMapping,
) -> PriorityMappingConfig:
    if kind == "vendors":
        return PriorityMappingConfig(version=mapping_config.version, vendors=mapping)
    return PriorityMappingConfig(version=mapping_config.version, purchase_orders=mapping)


def _map_preview_record(
    kind: str,
    raw_record: dict[str, Any],
    mapping: PriorityEntityMapping,
    row_index: int,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    mapped: dict[str, Any] = {}

    external_id = _field_value(raw_record, mapping.external_id_field)
    if external_id in (None, ""):
        warnings.append(
            f"Row {row_index} is missing external ID field '{mapping.external_id_field}'."
        )
    if kind == "vendors":
        mapped["external_id"] = external_id
        _copy_mapped_field(mapped, raw_record, mapping, "name", "name", warnings, row_index)
        _copy_mapped_field(mapped, raw_record, mapping, "tax_id", "tax_id", warnings, row_index)
        _copy_mapped_field(mapped, raw_record, mapping, "email", "email", warnings, row_index)
        _copy_mapped_field(mapped, raw_record, mapping, "payment_terms", "payment_terms", warnings, row_index)
        return mapped, warnings

    mapped["external_id"] = external_id
    _copy_mapped_field(mapped, raw_record, mapping, "po_number", "po_number", warnings, row_index)
    _copy_mapped_field(
        mapped,
        raw_record,
        mapping,
        "vendor_external_id",
        "vendor_external_id",
        warnings,
        row_index,
    )
    _copy_mapped_field(mapped, raw_record, mapping, "status", "status", warnings, row_index)
    _copy_mapped_field(
        mapped,
        raw_record,
        mapping,
        "total_amount",
        "total_amount",
        warnings,
        row_index,
        numeric=True,
    )
    _copy_mapped_field(mapped, raw_record, mapping, "currency", "currency", warnings, row_index)
    return mapped, warnings


def _copy_mapped_field(
    mapped: dict[str, Any],
    raw_record: dict[str, Any],
    mapping: PriorityEntityMapping,
    apflow_field: str,
    output_field: str,
    warnings: list[str],
    row_index: int,
    *,
    numeric: bool = False,
) -> None:
    priority_field = mapping.fields.get(apflow_field)
    if not priority_field:
        mapped[output_field] = None
        return
    value = _field_value(raw_record, priority_field)
    if value in (None, ""):
        warnings.append(
            f"Row {row_index} is missing mapped field '{priority_field}' for '{apflow_field}'."
        )
        mapped[output_field] = None
        return
    mapped[output_field] = _safe_number(value) if numeric else value


def _field_value(raw_record: dict[str, Any], field_name: str) -> Any:
    return raw_record.get(field_name)


def _safe_number(value: Any) -> float | int | str:
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        stripped = value.replace(",", "").strip()
        try:
            return float(stripped)
        except ValueError:
            return value
    return value
