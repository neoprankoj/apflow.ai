from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from app.core.schemas import CanonicalInvoice, InvoiceLineItem, InvoiceNormalizationOutput
from main import create_app


@pytest.fixture
def auth_enabled() -> Iterator[None]:
    previous = {
        "auth_enabled": settings.auth_enabled,
        "demo_mode": settings.demo_mode,
        "use_in_memory_repositories": settings.use_in_memory_repositories,
        "document_storage_provider": settings.document_storage_provider,
    }
    settings.auth_enabled = True
    settings.demo_mode = False
    settings.use_in_memory_repositories = True
    settings.document_storage_provider = "memory"
    _clear_dependency_caches()
    yield
    for key, value in previous.items():
        setattr(settings, key, value)
    _clear_dependency_caches()


def test_compliance_profiles_are_validation_only(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "compliance-profiles@example.com")

    response = client.get("/compliance/profiles", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    profiles = {profile["key"]: profile for profile in response.json()}
    assert {"generic_b2b", "israel_basic", "eu_vat_basic", "us_basic"}.issubset(profiles)
    assert all(profile["validation_only"] for profile in profiles.values())
    assert not any(profile["certified_integration"] for profile in profiles.values())


def test_generic_b2b_passes_with_required_fields(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "compliance-pass@example.com")
    invoice_id = _seed_invoice(dependencies.get_repository(), UUID(owner["tenant"]["id"]))

    response = client.get(
        f"/compliance/invoices/{invoice_id}?tenant_id={owner['tenant']['id']}&profile_key=generic_b2b",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"compliant_for_profile", "needs_review"}
    assert body["missing_required_fields"] == []
    assert "government" in body["legal_disclaimer"].casefold()


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("supplier_name", {"supplier_name": ""}),
        ("invoice_number", {"invoice_number": ""}),
        ("invoice_date", {"invoice_date": ""}),
        ("currency", {"currency": ""}),
        ("grand_total", {"grand_total": 0}),
    ],
)
def test_generic_b2b_fails_missing_required_fields(auth_enabled, field: str, kwargs: dict):
    client = TestClient(create_app())
    owner = _register(client, f"compliance-missing-{field}@example.com")
    invoice_id = _seed_invoice(dependencies.get_repository(), UUID(owner["tenant"]["id"]), **kwargs)

    response = client.get(
        f"/compliance/invoices/{invoice_id}?tenant_id={owner['tenant']['id']}&profile_key=generic_b2b",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_compliant"
    assert field in body["missing_required_fields"]


def test_eu_vat_profile_flags_missing_tax_and_vat_fields(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "compliance-eu@example.com")
    invoice_id = _seed_invoice(
        dependencies.get_repository(),
        UUID(owner["tenant"]["id"]),
        supplier_tax_id=None,
        tax_total=0,
        subtotal=100,
        grand_total=100,
    )

    response = client.get(
        f"/compliance/invoices/{invoice_id}?tenant_id={owner['tenant']['id']}&profile_key=eu_vat_basic",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_compliant"
    assert "supplier_tax_id" in body["missing_required_fields"]
    assert any(check["field"] == "tax_total" and check["status"] == "fail" for check in body["checks"])


def test_israel_basic_checks_supplier_tax_id(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "compliance-israel@example.com")
    invoice_id = _seed_invoice(dependencies.get_repository(), UUID(owner["tenant"]["id"]), supplier_tax_id=None)

    response = client.get(
        f"/compliance/invoices/{invoice_id}?tenant_id={owner['tenant']['id']}&profile_key=israel_basic",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert "supplier_tax_id" in response.json()["missing_required_fields"]


def test_compliance_summary_counts_statuses(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "compliance-summary@example.com")
    repository = dependencies.get_repository()
    tenant_id = UUID(owner["tenant"]["id"])
    _seed_invoice(repository, tenant_id)
    _seed_invoice(repository, tenant_id, invoice_number="")

    response = client.get(
        f"/compliance/summary?tenant_id={tenant_id}&profile_key=generic_b2b",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_checked"] == 2
    assert body["not_compliant_count"] == 1
    assert body["common_missing_fields"]["invoice_number"] == 1


def test_empty_compliance_summary_is_zero_safe(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "compliance-empty@example.com")

    response = client.get(
        f"/compliance/summary?tenant_id={owner['tenant']['id']}&profile_key=generic_b2b",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["total_checked"] == 0


def test_compliance_requires_auth_and_tenant_scope(auth_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "compliance-a@example.com")
    owner_b = _register(client, "compliance-b@example.com")
    invoice_id = _seed_invoice(dependencies.get_repository(), UUID(owner_a["tenant"]["id"]))

    unauthenticated = client.get(f"/compliance/summary?tenant_id={owner_a['tenant']['id']}")
    cross_tenant = client.get(
        f"/compliance/invoices/{invoice_id}?tenant_id={owner_a['tenant']['id']}",
        headers=_auth_headers(owner_b["access_token"]),
    )

    assert unauthenticated.status_code == 401
    assert cross_tenant.status_code == 403


def test_compliance_response_does_not_expose_raw_payloads_or_tokens(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "compliance-safe@example.com")
    invoice_id = _seed_invoice(dependencies.get_repository(), UUID(owner["tenant"]["id"]))

    response = client.get(
        f"/compliance/invoices/{invoice_id}?tenant_id={owner['tenant']['id']}&profile_key=generic_b2b",
        headers=_auth_headers(owner["access_token"]),
    )

    serialized = response.text.casefold()
    assert response.status_code == 200
    assert "access_token" not in serialized
    assert "token_hash" not in serialized
    assert "raw_provider" not in serialized
    assert "secret" not in serialized


def test_product_readiness_reflects_compliance_foundation(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "compliance-readiness@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    checks = {item["key"]: item for item in response.json()["checks"]}
    assert checks["compliance_validation_foundation_available"]["status"] == "pass"
    assert checks["certified_einvoicing_submission_available"]["status"] == "fail"
    assert checks["peppol_network_integration"]["status"] == "fail"


def _seed_invoice(repository, tenant_id: UUID, **overrides) -> UUID:
    invoice_id = uuid4()
    values = {
        "invoice_number": "C-100",
        "supplier_name": "Compliance Supplier",
        "supplier_tax_id": "VAT-123",
        "invoice_date": "2026-05-01",
        "currency": "USD",
        "subtotal": 100.0,
        "tax_total": 17.0,
        "shipping_amount": 0.0,
        "fee_total": 0.0,
        "discount_total": 0.0,
        "grand_total": 117.0,
        "line_items": [InvoiceLineItem(description="Service", quantity=1, unit_price=100, total=100)],
    }
    values.update(overrides)
    repository.store_invoice(
        InvoiceNormalizationOutput(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            canonical_invoice=CanonicalInvoice(**values),
        )
    )
    return invoice_id


def _register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/auth/register-demo-tenant",
        json={
            "tenant_name": f"Tenant {email}",
            "tenant_slug": email.split("@")[0].replace("_", "-"),
            "email": email,
            "full_name": "Owner User",
            "password": "password-123",
        },
    )
    assert response.status_code == 200
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _clear_dependency_caches() -> None:
    for provider in (
        dependencies.get_repository,
        dependencies.get_in_memory_repository,
        dependencies.get_audit_agent,
        dependencies.get_monitoring_agent,
        dependencies.get_error_handler_agent,
        dependencies.get_auth_service,
        dependencies.get_storage_adapter,
    ):
        provider.cache_clear()
