from uuid import uuid4

import httpx
import pytest

from app.agents.data.erp_connector_agent import ERPConnectorAgent
from app.core.config import Settings, settings
from app.core.schemas import ERPAdapterType, ERPOperation, ERPSyncRequest, ERPSyncStatus
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
        _real_settings(priority_erp_vendors_entity_name="SUPPLIERS"),
        client_factory=_client_factory(
            lambda _request: httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "external_id": "SUP-100",
                            "name": "Demo Supplier",
                            "tax_id": "TAX-100",
                            "email": "ap@example.test",
                            "payment_terms": "Net 30",
                        }
                    ]
                },
            )
        ),
    )

    vendors = adapter.sync_vendors(uuid4())

    assert vendors[0].external_vendor_id == "SUP-100"
    assert vendors[0].email == "ap@example.test"
    assert vendors[0].payment_terms == "Net 30"


def test_priority_real_adapter_maps_mocked_purchase_order_rows():
    adapter = PriorityODataAdapter(
        _real_settings(priority_erp_purchase_orders_entity_name="PURCHASEORDERS"),
        client_factory=_client_factory(
            lambda _request: httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "external_id": "PO-EXT-100",
                            "po_number": "PO-100",
                            "external_vendor_id": "SUP-100",
                            "vendor_name": "Demo Supplier",
                            "vendor_tax_id": "TAX-100",
                            "currency": "USD",
                            "total_amount": 1170,
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
    )

    purchase_orders = adapter.sync_purchase_orders(uuid4())

    assert purchase_orders[0].external_po_id == "PO-EXT-100"
    assert purchase_orders[0].lines[0].total == 1170


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
