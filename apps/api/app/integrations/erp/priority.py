from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx

from app.core.config import Settings
from app.core.schemas import (
    CanonicalInvoice,
    ERPAdapterType,
    ERPInvoiceExportResult,
    ERPPaymentStatusResult,
    ERPPurchaseOrderRecord,
    ERPSyncLog,
    ERPVendorRecord,
    PriorityEntityMapping,
    PriorityMappingConfig,
    PurchaseOrderLine,
)
from app.integrations.erp.base import ERPAdapterError
from app.integrations.erp.priority_mapping import build_priority_invoice_payload

PriorityClientFactory = Callable[..., httpx.Client]


class PriorityODataAdapter:
    """Production-shaped Priority OData adapter with safe mapping guards."""

    def __init__(
        self,
        app_settings: Settings,
        client_factory: PriorityClientFactory = httpx.Client,
        mapping_config: PriorityMappingConfig | None = None,
    ) -> None:
        self.settings = app_settings
        self.client_factory = client_factory
        self.mapping_config = mapping_config

    def with_mapping_config(self, mapping_config: PriorityMappingConfig | None) -> "PriorityODataAdapter":
        return PriorityODataAdapter(
            self.settings,
            client_factory=self.client_factory,
            mapping_config=mapping_config,
        )

    def get_adapter_name(self) -> str:
        return ERPAdapterType.PRIORITY

    def get_mode(self) -> str:
        return "real"

    def is_configured(self) -> bool:
        return self._configuration_status()["status"] == "ok"

    def service_root_url(self) -> str:
        return self.settings.priority_erp_base_url.rstrip("/")

    def metadata_url(self) -> str:
        return f"{self.service_root_url()}/$metadata"

    def test_connection(self, tenant_id: UUID) -> dict[str, Any]:
        del tenant_id
        configuration = self._configuration_status()
        if configuration["status"] != "ok":
            return configuration

        try:
            with self._client() as client:
                service_root = client.get(self.service_root_url())
                if service_root.status_code in {401, 403}:
                    return self._connection_result(
                        "unauthorized",
                        "Priority rejected the configured credentials.",
                        metadata_available=False,
                    )
                if service_root.status_code != 200:
                    return self._connection_result(
                        "connection_failed",
                        f"Priority service root returned HTTP {service_root.status_code}.",
                        metadata_available=False,
                    )
                try:
                    payload = service_root.json()
                except ValueError:
                    return self._connection_result(
                        "invalid_response",
                        "Priority service root did not return JSON.",
                        metadata_available=False,
                    )
                if not isinstance(payload, dict) or "value" not in payload:
                    return self._connection_result(
                        "invalid_response",
                        "Priority service root response did not include the OData resource list.",
                        metadata_available=False,
                    )

                metadata = client.get(self.metadata_url())
                metadata_available = metadata.status_code == 200
                return self._connection_result(
                    "ok",
                    "Priority OData service root is reachable.",
                    metadata_available=metadata_available,
                    service_collection_count=len(payload.get("value") or []),
                )
        except httpx.RequestError as exc:
            return self._connection_result(
                "connection_failed",
                f"Priority connection failed: {exc.__class__.__name__}.",
                metadata_available=False,
            )

    def sync_vendors(self, tenant_id: UUID) -> list[ERPVendorRecord]:
        mapping = self._entity_mapping("vendors")
        if mapping is None:
            raise self._mapping_required(
                "vendor",
                "Priority vendor entity mapping is not configured.",
            )
        return [
            self._vendor_record(tenant_id, row, mapping)
            for row in self._fetch_entity_rows(mapping.entity_name)
        ]

    def sync_purchase_orders(self, tenant_id: UUID) -> list[ERPPurchaseOrderRecord]:
        mapping = self._entity_mapping("purchase_orders")
        if mapping is None:
            raise self._mapping_required(
                "purchase_order",
                "Priority purchase-order entity mapping is not configured.",
            )
        return [
            self._purchase_order_record(tenant_id, row, mapping)
            for row in self._fetch_entity_rows(mapping.entity_name)
        ]

    def export_invoice(self, tenant_id: UUID, invoice_id: UUID) -> ERPInvoiceExportResult:
        del tenant_id, invoice_id
        if self._entity_mapping("invoice_export") is None:
            raise self._mapping_required(
                "invoice_export",
                "Priority real export requires invoice export mapping.",
            )
        raise ERPAdapterError(
            "dry_run_required",
            "Priority real export must be previewed before live writes are enabled.",
            {"provider": ERPAdapterType.PRIORITY, "mode": "real"},
        )

    def update_invoice_status(self, tenant_id: UUID, invoice_id: UUID, status: str) -> bool:
        del tenant_id, invoice_id, status
        raise self._mapping_required(
            "invoice_status",
            "Priority invoice-status mapping is not configured.",
        )

    def sync_payment_status(self, tenant_id: UUID, invoice_id: UUID) -> ERPPaymentStatusResult:
        del tenant_id, invoice_id
        raise self._mapping_required(
            "payment_status",
            "Priority payment-status mapping is not configured.",
        )

    def get_sync_log(self, tenant_id: UUID) -> list[ERPSyncLog]:
        del tenant_id
        return []

    def _configuration_status(self) -> dict[str, Any]:
        parsed = urlparse(self.service_root_url())
        if not self.settings.priority_erp_base_url:
            return self._connection_result(
                "missing_credentials",
                "Priority base URL is not configured.",
                metadata_available=False,
            )
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return self._connection_result(
                "invalid_base_url",
                "Priority base URL must be an absolute HTTP(S) URL.",
                metadata_available=False,
            )
        if not self.settings.priority_erp_username or not self._password():
            return self._connection_result(
                "missing_credentials",
                "Priority username and password or token are not configured.",
                metadata_available=False,
            )
        return self._connection_result(
            "ok",
            "Priority configuration is present.",
            metadata_available=False,
        )

    def _connection_result(
        self,
        status: str,
        message: str,
        *,
        metadata_available: bool,
        service_collection_count: int | None = None,
    ) -> dict[str, Any]:
        host = urlparse(self.service_root_url()).hostname
        result = {
            "provider": ERPAdapterType.PRIORITY,
            "mode": "real",
            "status": status,
            "message": message,
            "base_url_host": host,
            "timeout_seconds": self.settings.priority_erp_timeout_seconds,
            "metadata_available": metadata_available,
        }
        if service_collection_count is not None:
            result["service_collection_count"] = service_collection_count
        return result

    def _client(self) -> httpx.Client:
        return self.client_factory(
            timeout=self.settings.priority_erp_timeout_seconds,
            verify=self.settings.priority_erp_verify_tls,
            auth=httpx.BasicAuth(
                self.settings.priority_erp_username,
                self._password(),
            ),
            headers={"Accept": "application/json"},
        )

    def _password(self) -> str:
        return self.settings.priority_erp_password or self.settings.priority_erp_api_key

    def _fetch_entity_rows(self, entity_name: str) -> list[dict[str, Any]]:
        if not self.is_configured():
            raise ERPAdapterError(
                "missing_credentials",
                "Priority credentials are not configured.",
                self._configuration_status(),
            )
        try:
            with self._client() as client:
                response = client.get(
                    f"{self.service_root_url()}/{entity_name}",
                    params={"$top": 50},
                )
        except httpx.RequestError as exc:
            raise ERPAdapterError(
                "connection_failed",
                f"Priority entity request failed: {exc.__class__.__name__}.",
                {"provider": ERPAdapterType.PRIORITY, "mode": "real", "entity_name": entity_name},
            ) from exc
        if response.status_code in {401, 403}:
            raise ERPAdapterError(
                "unauthorized",
                "Priority rejected the configured credentials.",
                {"provider": ERPAdapterType.PRIORITY, "mode": "real", "entity_name": entity_name},
            )
        if response.status_code != 200:
            raise ERPAdapterError(
                "connection_failed",
                f"Priority entity request returned HTTP {response.status_code}.",
                {"provider": ERPAdapterType.PRIORITY, "mode": "real", "entity_name": entity_name},
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ERPAdapterError(
                "invalid_response",
                "Priority entity response did not return JSON.",
                {"provider": ERPAdapterType.PRIORITY, "mode": "real", "entity_name": entity_name},
            ) from exc
        rows = payload.get("value")
        if not isinstance(rows, list):
            raise ERPAdapterError(
                "invalid_response",
                "Priority entity response did not include a row list.",
                {"provider": ERPAdapterType.PRIORITY, "mode": "real", "entity_name": entity_name},
            )
        return [row for row in rows if isinstance(row, dict)]

    def build_invoice_payload(self, invoice: CanonicalInvoice) -> dict[str, Any]:
        mapping = self._entity_mapping("invoice_export")
        if mapping is None:
            raise self._mapping_required(
                "invoice_export",
                "Priority real export requires invoice export mapping.",
            )
        return build_priority_invoice_payload(invoice, mapping)

    def _vendor_record(
        self,
        tenant_id: UUID,
        row: dict[str, Any],
        mapping: PriorityEntityMapping,
    ) -> ERPVendorRecord:
        return ERPVendorRecord(
            tenant_id=tenant_id,
            external_vendor_id=str(self._first(row, mapping.external_id_field)),
            name=str(self._mapped_required(row, mapping, "name")),
            tax_id=self._mapped_optional(row, mapping, "tax_id"),
            email=self._mapped_optional(row, mapping, "email"),
            payment_terms=self._mapped_optional(row, mapping, "payment_terms"),
        )

    def _purchase_order_record(
        self,
        tenant_id: UUID,
        row: dict[str, Any],
        mapping: PriorityEntityMapping,
    ) -> ERPPurchaseOrderRecord:
        lines = [
            PurchaseOrderLine(
                description=str(self._first(line, "description", "DESCRIPTION")),
                quantity=float(self._first(line, "quantity", "QUANTITY")),
                unit_price=float(self._first(line, "unit_price", "PRICE")),
                total=float(self._first(line, "total", "TOTAL")),
            )
            for line in row.get("lines", [])
            if isinstance(line, dict)
        ]
        external_vendor_id = str(self._mapped_required(row, mapping, "vendor_external_id"))
        return ERPPurchaseOrderRecord(
            tenant_id=tenant_id,
            external_po_id=str(self._first(row, mapping.external_id_field)),
            po_number=str(self._mapped_required(row, mapping, "po_number")),
            external_vendor_id=external_vendor_id,
            vendor_name=str(self._mapped_optional(row, mapping, "vendor_name") or external_vendor_id),
            vendor_tax_id=self._mapped_optional(row, mapping, "vendor_tax_id"),
            currency=str(self._mapped_optional(row, mapping, "currency") or "USD"),
            total_amount=float(self._mapped_optional(row, mapping, "total_amount") or 0),
            lines=lines,
        )

    def _entity_mapping(self, section: str) -> PriorityEntityMapping | None:
        mapping = getattr(self.mapping_config, section, None)
        if mapping is None or not mapping.enabled:
            return None
        return mapping

    def _mapping_required(self, mapping: str, message: str) -> ERPAdapterError:
        return ERPAdapterError(
            "mapping_required",
            message,
            {
                "provider": ERPAdapterType.PRIORITY,
                "mode": "real",
                "mapping": mapping,
            },
        )

    def _first(self, row: dict[str, Any], *keys: str) -> Any:
        value = self._optional(row, *keys)
        if value in (None, ""):
            raise ERPAdapterError(
                "invalid_response",
                f"Priority row is missing required fields: {', '.join(keys)}.",
                {"provider": ERPAdapterType.PRIORITY, "mode": "real"},
            )
        return value

    def _optional(self, row: dict[str, Any], *keys: str) -> Any | None:
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return row[key]
        return None

    def _mapped_required(
        self,
        row: dict[str, Any],
        mapping: PriorityEntityMapping,
        apflow_field: str,
    ) -> Any:
        priority_field = mapping.fields.get(apflow_field)
        if not priority_field:
            raise self._mapping_required(
                apflow_field,
                f"Priority mapping is missing required field '{apflow_field}'.",
            )
        return self._first(row, priority_field)

    def _mapped_optional(
        self,
        row: dict[str, Any],
        mapping: PriorityEntityMapping,
        apflow_field: str,
    ) -> Any | None:
        priority_field = mapping.fields.get(apflow_field)
        if not priority_field:
            return None
        return self._optional(row, priority_field)
