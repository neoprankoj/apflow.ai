from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.schemas import (
    CanonicalInvoice,
    PriorityEntityMapping,
    PriorityImportPlanItem,
    PriorityImportPlanResponse,
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

    message = (
        "Read-only Priority preview generated. No data was imported and no Priority data was changed."
        if source == "priority"
        else f"Preview generated from {source} records. No data was imported."
    )
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
        message=message,
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


def build_vendor_import_plan(
    mapped_records: list[dict[str, Any]],
    existing_vendors: list[Any],
    external_vendor_ids: dict[Any, str] | None = None,
    *,
    kind: str = "vendors",
    mode: str = "mock",
    source: str = "sample",
    inherited_warnings: list[str] | None = None,
) -> PriorityImportPlanResponse:
    external_vendor_ids = external_vendor_ids or {}
    items = [
        _vendor_import_plan_item(mapped, existing_vendors, external_vendor_ids)
        for mapped in mapped_records
    ]
    return _plan_response(
        kind=kind,
        mode=mode,
        source=source,
        items=items,
        warnings=inherited_warnings or [],
    )


def build_purchase_order_import_plan(
    mapped_records: list[dict[str, Any]],
    existing_purchase_orders: list[Any],
    external_purchase_order_ids: dict[Any, str] | None = None,
    *,
    kind: str = "purchase_orders",
    mode: str = "mock",
    source: str = "sample",
    inherited_warnings: list[str] | None = None,
) -> PriorityImportPlanResponse:
    external_purchase_order_ids = external_purchase_order_ids or {}
    items = [
        _purchase_order_import_plan_item(mapped, existing_purchase_orders, external_purchase_order_ids)
        for mapped in mapped_records
    ]
    return _plan_response(
        kind=kind,
        mode=mode,
        source=source,
        items=items,
        warnings=inherited_warnings or [],
    )


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
    if isinstance(value, int | float | Decimal):
        return value
    if isinstance(value, str):
        stripped = value.replace(",", "").strip()
        try:
            return float(stripped)
        except ValueError:
            return value
    return value


def _vendor_import_plan_item(
    mapped: dict[str, Any],
    existing_vendors: list[Any],
    external_vendor_ids: dict[Any, str],
) -> PriorityImportPlanItem:
    external_id = _string_or_none(mapped.get("external_id"))
    matches = _vendor_matches(mapped, existing_vendors, external_vendor_ids)
    if len(matches) > 1:
        return PriorityImportPlanItem(
            action="would_conflict",
            reason="Multiple existing vendors could match this Priority record.",
            mapped_record=mapped,
            matched_existing_id=None,
            diff=None,
            warnings=["Review matching fields before enabling import."],
        )
    if not matches:
        return PriorityImportPlanItem(
            action="would_create",
            reason=(
                f"No existing vendor matched external_id {external_id}."
                if external_id
                else "No existing vendor matched this record."
            ),
            mapped_record=mapped,
        )

    existing = matches[0]
    diff = _vendor_diff(mapped, existing)
    existing_id = str(getattr(existing, "vendor_id"))
    if diff:
        return PriorityImportPlanItem(
            action="would_update",
            reason="Existing vendor matched, but mapped fields differ.",
            mapped_record=mapped,
            matched_existing_id=existing_id,
            diff=diff,
        )
    return PriorityImportPlanItem(
        action="would_skip",
        reason="Existing vendor already matches mapped fields.",
        mapped_record=mapped,
        matched_existing_id=existing_id,
        diff=None,
    )


def _purchase_order_import_plan_item(
    mapped: dict[str, Any],
    existing_purchase_orders: list[Any],
    external_purchase_order_ids: dict[Any, str],
) -> PriorityImportPlanItem:
    external_id = _string_or_none(mapped.get("external_id"))
    po_number = _string_or_none(mapped.get("po_number"))
    matches = _purchase_order_matches(mapped, existing_purchase_orders, external_purchase_order_ids)
    if len(matches) > 1:
        return PriorityImportPlanItem(
            action="would_conflict",
            reason="Multiple existing purchase orders could match this Priority record.",
            mapped_record=mapped,
            matched_existing_id=None,
            diff=None,
            warnings=["Review PO number and external ID before enabling import."],
        )
    if not matches:
        return PriorityImportPlanItem(
            action="would_create",
            reason=(
                f"No existing purchase order matched {po_number or external_id}."
                if po_number or external_id
                else "No existing purchase order matched this record."
            ),
            mapped_record=mapped,
        )

    existing = matches[0]
    diff = _purchase_order_diff(mapped, existing)
    existing_id = str(getattr(existing, "purchase_order_id"))
    if diff:
        return PriorityImportPlanItem(
            action="would_update",
            reason="Existing purchase order matched, but mapped fields differ.",
            mapped_record=mapped,
            matched_existing_id=existing_id,
            diff=diff,
        )
    return PriorityImportPlanItem(
        action="would_skip",
        reason="Existing purchase order already matches mapped fields.",
        mapped_record=mapped,
        matched_existing_id=existing_id,
        diff=None,
    )


def _plan_response(
    *,
    kind: str,
    mode: str,
    source: str,
    items: list[PriorityImportPlanItem],
    warnings: list[str],
) -> PriorityImportPlanResponse:
    summary = {
        "would_create": 0,
        "would_update": 0,
        "would_skip": 0,
        "would_conflict": 0,
    }
    for item in items:
        summary[item.action] = summary.get(item.action, 0) + 1
    return PriorityImportPlanResponse(
        status="plan_ready",
        kind=kind,
        mode=mode,
        source=source,
        records_planned=len(items),
        summary=summary,
        items=items,
        warnings=warnings,
        errors=[],
        message="Import plan generated. No data was imported.",
    )


def _vendor_matches(
    mapped: dict[str, Any],
    existing_vendors: list[Any],
    external_vendor_ids: dict[Any, str],
) -> list[Any]:
    external_id = _normalize(mapped.get("external_id"))
    if external_id:
        external_matches = [
            vendor
            for vendor in existing_vendors
            if _normalize(external_vendor_ids.get(getattr(vendor, "vendor_id"))) == external_id
        ]
        if external_matches:
            return external_matches

    possible_matches = []
    tax_id = _normalize(mapped.get("tax_id"))
    name = _normalize(mapped.get("name"))
    for vendor in existing_vendors:
        vendor_tax_id = _normalize(getattr(vendor, "tax_id", None))
        vendor_name = _normalize(getattr(vendor, "name", None))
        if tax_id and vendor_tax_id == tax_id:
            possible_matches.append(vendor)
            continue
        if name and vendor_name == name:
            possible_matches.append(vendor)
    return possible_matches


def _purchase_order_matches(
    mapped: dict[str, Any],
    existing_purchase_orders: list[Any],
    external_purchase_order_ids: dict[Any, str],
) -> list[Any]:
    external_id = _normalize(mapped.get("external_id"))
    if external_id:
        external_matches = [
            po
            for po in existing_purchase_orders
            if _normalize(external_purchase_order_ids.get(getattr(po, "purchase_order_id"))) == external_id
        ]
        if external_matches:
            return external_matches

    po_number = _normalize(mapped.get("po_number"))
    if not po_number:
        return []
    return [
        po
        for po in existing_purchase_orders
        if _normalize(getattr(po, "po_number", None)) == po_number
    ]


def _vendor_diff(mapped: dict[str, Any], existing: Any) -> dict[str, Any] | None:
    diff = _field_diff("name", mapped.get("name"), getattr(existing, "name", None))
    tax_diff = _field_diff("tax_id", mapped.get("tax_id"), getattr(existing, "tax_id", None))
    diff.update(tax_diff)
    return diff or None


def _purchase_order_diff(mapped: dict[str, Any], existing: Any) -> dict[str, Any] | None:
    diff: dict[str, Any] = {}
    for field_name in ("po_number", "currency", "status"):
        diff.update(_field_diff(field_name, mapped.get(field_name), getattr(existing, field_name, None)))
    diff.update(_field_diff("total_amount", mapped.get("total_amount"), getattr(existing, "total_amount", None)))
    return diff or None


def _field_diff(field_name: str, incoming: Any, existing: Any) -> dict[str, Any]:
    if _compare_value(incoming) == _compare_value(existing):
        return {}
    return {
        field_name: {
            "existing": existing,
            "incoming": incoming,
        }
    }


def _compare_value(value: Any) -> str:
    if isinstance(value, int | float | Decimal):
        return f"{float(value):.4f}"
    return _normalize(value)


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


def _string_or_none(value: Any) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None
