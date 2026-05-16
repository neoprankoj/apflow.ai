from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.core.config import settings
from app.core.schemas import (
    ApprovalRoute,
    ApprovalTaskStatus,
    CanonicalInvoice,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
)
from app.db.models import Base
from app.db.repositories import SQLAlchemyAPRepository
from main import create_app


@pytest.fixture
def sql_app(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    previous_auth_enabled = settings.auth_enabled
    previous_demo_mode = settings.demo_mode
    previous_use_in_memory = settings.use_in_memory_repositories
    settings.auth_enabled = True
    settings.demo_mode = False
    settings.use_in_memory_repositories = False
    dependencies.clear_dependency_caches()

    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'request-scoped.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_db_session():
        session = session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[dependencies.get_db_session] = override_db_session
    with TestClient(app) as client:
        yield client, session_factory

    settings.auth_enabled = previous_auth_enabled
    settings.demo_mode = previous_demo_mode
    settings.use_in_memory_repositories = previous_use_in_memory
    dependencies.clear_dependency_caches()


@pytest.mark.parametrize("action", ["approve", "reject", "hold"])
def test_parallel_protected_refreshes_are_safe_after_approval_decisions(sql_app, action):
    client, session_factory = sql_app
    owner = _register(client, f"{action}-parallel-owner@example.com")
    invoice_id = _seed_blocked_invoice(session_factory, owner["tenant"]["id"])
    headers = _auth_headers(owner["access_token"])
    tenant_id = owner["tenant"]["id"]

    decision = client.post(
        f"/invoices/{invoice_id}/approval-decision",
        json={"tenant_id": tenant_id, "action": action},
        headers=headers,
    )

    assert decision.status_code == 200

    endpoints = (
        "/admin/users",
        f"/review/tasks?tenant_id={tenant_id}",
        f"/invoices?tenant_id={tenant_id}",
        f"/invoices/workflows?tenant_id={tenant_id}",
        f"/invoices/approval-tasks?tenant_id={tenant_id}",
        f"/invoices/notification-events?tenant_id={tenant_id}",
    )
    with ThreadPoolExecutor(max_workers=len(endpoints)) as executor:
        responses = list(executor.map(lambda endpoint: client.get(endpoint, headers=headers), endpoints))

    assert [response.status_code for response in responses] == [200] * len(endpoints)


def _seed_blocked_invoice(session_factory: sessionmaker, tenant_id: str) -> UUID:
    with session_factory() as session:
        repository = SQLAlchemyAPRepository(session)
        tenant_uuid = UUID(tenant_id)
        vendor = repository.add_vendor(tenant_uuid, "Blocked Vendor")
        output = InvoiceNormalizationOutput(
            tenant_id=tenant_uuid,
            canonical_invoice=CanonicalInvoice(
                invoice_number=f"INV-BLOCKED-{uuid4()}",
                supplier_name="Blocked Vendor",
                invoice_date="2026-05-16",
                currency="USD",
                subtotal=100,
                tax_total=17,
                grand_total=117,
                line_items=[
                    InvoiceLineItem(
                        description="Blocked service",
                        quantity=1,
                        unit_price=100,
                        tax_amount=17,
                        total=117,
                    )
                ],
            ),
        )
        repository.store_invoice(output)
        repository.update_invoice_vendor(tenant_uuid, output.invoice_id, vendor.vendor_id)
        repository.create_approval_task(
            tenant_id=tenant_uuid,
            invoice_id=output.invoice_id,
            route=ApprovalRoute.BLOCKED,
            assigned_role="ap_admin",
            status=ApprovalTaskStatus.BLOCKED,
            reason="High-risk invoice requires review.",
        )
        return output.invoice_id


def _register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/auth/register-demo-tenant",
        json={
            "tenant_name": f"Tenant {email}",
            "tenant_slug": email.split("@")[0],
            "email": email,
            "full_name": "Owner User",
            "password": "password-123",
        },
    )
    assert response.status_code == 200
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
