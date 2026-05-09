from fastapi.testclient import TestClient

from main import create_app


def _tenant() -> str:
    return "22222222-2222-2222-2222-222222222222"


def test_erp_adapters_endpoint_returns_mock_adapters():
    client = TestClient(create_app())

    response = client.get("/erp/adapters")

    assert response.status_code == 200
    assert {"priority", "odoo", "zoho_books"}.issubset(set(response.json()))


def test_erp_test_connection_endpoint_succeeds():
    client = TestClient(create_app())

    response = client.post("/erp/test-connection", json={"tenant_id": _tenant(), "adapter_type": "priority"})

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_erp_sync_purchase_orders_endpoint_populates_pos():
    client = TestClient(create_app())
    tenant_id = _tenant()

    response = client.post(
        "/erp/sync-purchase-orders",
        json={"tenant_id": tenant_id, "adapter_type": "priority"},
    )
    pos = client.get(f"/invoices/purchase-orders?tenant_id={tenant_id}")

    assert response.status_code == 200
    assert response.json()["records_processed"] >= 1
    assert pos.status_code == 200
    assert len(pos.json()) >= 1


def test_erp_export_invoice_endpoint_exports_full_pipeline_invoice():
    client = TestClient(create_app())
    tenant_id = _tenant()
    pipeline = client.post(
        "/invoices/full-mock-pipeline",
        json={
            "tenant_id": tenant_id,
            "source": "upload",
            "file_url": "mock://incoming/invoice.pdf",
            "metadata": {
                "sender_email": "ap@example.com",
                "original_filename": "invoice.pdf",
                "mime_type": "application/pdf",
            },
            "content": (
                "invoice_number=INV-ERP-API supplier_name=Northstar Components "
                "supplier_tax_id=TAX-12345 subtotal=1000 tax_total=170 grand_total=1170 "
                "currency=USD invoice_date=2026-05-05 po_number=PO-100"
            ),
        },
    )
    invoice_id = pipeline.json()["invoice"]["invoice_id"]

    response = client.post(
        "/erp/export-invoice",
        json={"tenant_id": tenant_id, "adapter_type": "priority", "invoice_id": invoice_id},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["external_id"]


def test_erp_sync_logs_endpoint_returns_tenant_logs():
    client = TestClient(create_app())
    tenant_id = _tenant()
    client.post("/erp/test-connection", json={"tenant_id": tenant_id, "adapter_type": "priority"})

    response = client.get(f"/erp/sync-logs?tenant_id={tenant_id}")

    assert response.status_code == 200
    assert len(response.json()) >= 1
