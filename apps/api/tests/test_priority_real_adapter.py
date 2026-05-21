from uuid import uuid4

import httpx
import pytest

from app.agents.data.erp_connector_agent import ERPConnectorAgent
from app.core.config import Settings, settings
from app.core.schemas import (
    CanonicalInvoice,
    ERPAdapterType,
    ERPConnectionConfig,
    ERPOperation,
    ERPSyncRequest,
    ERPSyncStatus,
    InvoiceNormalizationOutput,
    PriorityEntityMapping,
    PriorityMappingConfig,
)
from app.integrations.erp.base import ERPAdapterError
from app.integrations.erp.priority import PriorityODataAdapter


def _client_factory(handler):
    def factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def _real_settings(**overrides) -> Settings:
    return Settings(
        priority_erp_mode="real",
        priority_erp_base_url="https://priority.example.test/odata/Priority/tabula.ini/demo",
        priority_erp_username="api-user",
        priority_erp_password="super-secret-password",
        **overrides,
    )


def _mapping_config() -> PriorityMappingConfig:
    return PriorityMappingConfig(
        vendors=PriorityEntityMapping(
            entity_name="SUPPLIERS",
            external_id_field="SUPNAME",
            fields={
                "name": "SUPDES",
                "tax_id": "VATNUM",
                "email": "EMAIL",
                "payment_terms": "PAYCODE",
            },
        ),
        purchase_orders=PriorityEntityMapping(
            entity_name="PORDERS",
            external_id_field="ORDNAME",
            fields={
                "po_number": "ORDNAME",
                "vendor_external_id": "SUPNAME",
                "vendor_name": "SUPDES",
                "vendor_tax_id": "VATNUM",
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
                "description": "DETAILS",
            },
        ),
    )


def test_priority_real_adapter_reports_missing_credentials():
    adapter = PriorityODataAdapter(Settings(priority_erp_mode="real"))

    result = adapter.test_connection(uuid4())

    assert result["status"] == "missing_credentials"
    assert "secret" not in str(result).lower()


def test_priority_real_adapter_rejects_invalid_base_url():
    adapter = PriorityODataAdapter(
        Settings(
            priority_erp_mode="real",
            priority_erp_base_url="not-a-url",
            priority_erp_username="api-user",
            priority_erp_password="secret",
        )
    )

    result = adapter.test_connection(uuid4())

    assert result["status"] == "invalid_base_url"


def test_priority_real_adapter_checks_service_root_and_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/$metadata"):
            return httpx.Response(200, text="<edmx />")
        return httpx.Response(200, json={"value": [{"name": "SUPPLIERS"}]})

    adapter = PriorityODataAdapter(_real_settings(), client_factory=_client_factory(handler))

    result = adapter.test_connection(uuid4())

    assert result["status"] == "ok"
    assert result["metadata_available"] is True
    assert result["service_collection_count"] == 1
    assert result["base_url_host"] == "priority.example.test"
    assert "super-secret-password" not in str(result)


def test_priority_real_adapter_maps_unauthorized_safely():
    adapter = PriorityODataAdapter(
        _real_settings(),
        client_factory=_client_factory(lambda _request: httpx.Response(401)),
    )

    result = adapter.test_connection(uuid4())

    assert result["status"] == "unauthorized"
    assert "super-secret-password" not in str(result)


def test_priority_real_adapter_requires_vendor_mapping():
    adapter = PriorityODataAdapter(_real_settings())

    with pytest.raises(ERPAdapterError, match="vendor entity mapping"):
        adapter.sync_vendors(uuid4())


def test_priority_real_adapter_requires_purchase_order_mapping():
    adapter = PriorityODataAdapter(_real_settings())

    with pytest.raises(ERPAdapterError, match="purchase-order entity mapping"):
        adapter.sync_purchase_orders(uuid4())


def test_priority_real_adapter_requires_invoice_export_mapping():
    adapter = PriorityODataAdapter(_real_settings())

    with pytest.raises(ERPAdapterError, match="requires invoice export mapping"):
        adapter.export_invoice(uuid4(), uuid4())


def test_priority_real_adapter_maps_mocked_vendor_rows():
    adapter = PriorityODataAdapter(
        _real_settings(),
        client_factory=_client_factory(
            lambda _request: httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "SUPNAME": "SUP-100",
                            "SUPDES": "Demo Supplier",
                            "VATNUM": "TAX-100",
                            "EMAIL": "ap@example.test",
                            "PAYCODE": "Net 30",
                        }
                    ]
                },
            )
        ),
        mapping_config=_mapping_config(),
    )

    vendors = adapter.sync_vendors(uuid4())

    assert vendors[0].external_vendor_id == "SUP-100"
    assert vendors[0].email == "ap@example.test"
    assert vendors[0].payment_terms == "Net 30"


def test_priority_read_only_fetch_uses_get_and_caps_limit():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"value": [{"SUPNAME": "SUP-1"}, {"SUPNAME": "SUP-2"}]})

    adapter = PriorityODataAdapter(
        _real_settings(priority_erp_max_preview_records=1),
        client_factory=_client_factory(handler),
    )

    rows = adapter.fetch_entity_rows_read_only("SUPPLIERS", limit=50)

    assert len(rows) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.params["$top"] == "1"


def test_priority_read_only_fetch_maps_unauthorized_safely():
    adapter = PriorityODataAdapter(
        _real_settings(),
        client_factory=_client_factory(lambda _request: httpx.Response(401)),
    )

    with pytest.raises(ERPAdapterError) as exc_info:
        adapter.fetch_entity_rows_read_only("SUPPLIERS")

    assert exc_info.value.code == "unauthorized"
    assert "super-secret-password" not in str(exc_info.value.details)


def test_priority_read_only_fetch_maps_missing_entity_safely():
    adapter = PriorityODataAdapter(
        _real_settings(),
        client_factory=_client_factory(lambda _request: httpx.Response(404)),
    )

    with pytest.raises(ERPAdapterError) as exc_info:
        adapter.fetch_entity_rows_read_only("MISSING")

    assert exc_info.value.code == "entity_not_found"


def test_priority_read_only_fetch_handles_invalid_shape():
    adapter = PriorityODataAdapter(
        _real_settings(),
        client_factory=_client_factory(lambda _request: httpx.Response(200, json={"unexpected": []})),
    )

    with pytest.raises(ERPAdapterError) as exc_info:
        adapter.fetch_entity_rows_read_only("SUPPLIERS")

    assert exc_info.value.code == "invalid_response"


def test_priority_real_adapter_maps_mocked_purchase_order_rows():
    adapter = PriorityODataAdapter(
        _real_settings(),
        client_factory=_client_factory(
            lambda _request: httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "ORDNAME": "PO-EXT-100",
                            "SUPNAME": "SUP-100",
                            "SUPDES": "Demo Supplier",
                            "VATNUM": "TAX-100",
                            "CODE": "USD",
                            "TOTPRICE": 1170,
                            "lines": [
                                {
                                    "description": "Office supplies",
                                    "quantity": 1,
                                    "unit_price": 1000,
                                    "total": 1170,
                                }
                            ],
                        }
                    ]
                },
            )
        ),
        mapping_config=_mapping_config(),
    )

    purchase_orders = adapter.sync_purchase_orders(uuid4())

    assert purchase_orders[0].external_po_id == "PO-EXT-100"
    assert purchase_orders[0].lines[0].total == 1170


def test_priority_real_adapter_builds_invoice_payload_preview():
    adapter = PriorityODataAdapter(_real_settings(), mapping_config=_mapping_config())
    invoice = CanonicalInvoice(
        invoice_number="INV-100",
        supplier_name="Demo Supplier",
        invoice_date="2026-05-18",
        currency="USD",
        subtotal=100,
        tax_total=17,
        grand_total=117,
    )

    payload = adapter.build_invoice_payload(invoice)

    assert payload["entity_name"] == "APINVOICES"
    assert payload["mapped_fields"]["IVNUM"] == "INV-100"
    assert payload["mapped_fields"]["TOTPRICE"] == 117
    assert payload["missing_fields"] == ["vendor_external_id"]


def test_priority_real_export_returns_write_disabled_with_preview(
    tenant_id,
    repository,
    audit_agent,
    monitoring_agent,
    error_handler_agent,
):
    mapping = _mapping_config()
    repository.set_erp_connection_config(
        ERPConnectionConfig(
            tenant_id=tenant_id,
            adapter_type=ERPAdapterType.PRIORITY,
            config={"priority_mapping": mapping.model_dump(mode="json")},
        )
    )
    invoice = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        canonical_invoice=CanonicalInvoice(
            invoice_number="INV-200",
            supplier_name="Demo Supplier",
            invoice_date="2026-05-18",
            currency="USD",
            subtotal=100,
            tax_total=17,
            grand_total=117,
        ),
    )
    repository.store_invoice(invoice)
    agent = ERPConnectorAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
        adapters={ERPAdapterType.PRIORITY: PriorityODataAdapter(_real_settings())},
    )

    result = agent.run(
        ERPSyncRequest(
            tenant_id=tenant_id,
            adapter_type=ERPAdapterType.PRIORITY,
            operation=ERPOperation.EXPORT_INVOICE,
            invoice_id=invoice.invoice_id,
        )
    )

    assert result.status == ERPSyncStatus.FAILED
    assert result.details["error_code"] == "write_disabled"
    assert result.details["payload_preview"]["mapped_fields"]["IVNUM"] == "INV-200"


def test_priority_real_mode_test_connection_returns_safe_failure(
    tenant_id,
    repository,
    audit_agent,
    monitoring_agent,
    error_handler_agent,
):
    adapter = PriorityODataAdapter(Settings(priority_erp_mode="real"))
    agent = ERPConnectorAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
        adapters={ERPAdapterType.PRIORITY: adapter},
    )

    result = agent.run(
        ERPSyncRequest(
            tenant_id=tenant_id,
            adapter_type=ERPAdapterType.PRIORITY,
            operation=ERPOperation.TEST_CONNECTION,
        )
    )

    assert result.status == ERPSyncStatus.FAILED
    assert result.details["error_code"] == "missing_credentials"
    assert "password" not in str(result.model_dump(mode="json")).lower()


def test_priority_mode_can_switch_default_adapter(
    monkeypatch,
    repository,
    audit_agent,
    monitoring_agent,
    error_handler_agent,
):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")

    agent = ERPConnectorAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )

    assert isinstance(agent.adapters[ERPAdapterType.PRIORITY], PriorityODataAdapter)
