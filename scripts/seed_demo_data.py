"""Seed a demo APFlow tenant through the running API.

The script does not print tokens or secrets. It creates or updates a demo
tenant owner, syncs mock ERP vendors/POs, and processes one deterministic
sample invoice.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed APFlow demo data through the API")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant-name", default="APFlow Demo Tenant")
    parser.add_argument("--tenant-slug", default="apflow-demo")
    parser.add_argument("--email", default="demo-owner@apflow.local")
    parser.add_argument("--password", default="demo-password-123")
    parser.add_argument("--adapter", default="priority")
    parser.add_argument("--skip-invoice", action="store_true")
    args = parser.parse_args()

    registered = post(
        args.api_base_url,
        "/auth/register-demo-tenant",
        {
            "tenant_name": args.tenant_name,
            "tenant_slug": args.tenant_slug,
            "email": args.email,
            "full_name": "Demo Owner",
            "password": args.password,
        },
    )
    token = registered["access_token"]
    tenant_id = registered["tenant"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    post(args.api_base_url, "/erp/sync-vendors", {"tenant_id": tenant_id, "adapter_type": args.adapter}, headers)
    post(args.api_base_url, "/erp/sync-purchase-orders", {"tenant_id": tenant_id, "adapter_type": args.adapter}, headers)

    invoice_id = None
    workflow_status = "not_processed"
    if not args.skip_invoice:
        pipeline = post(
            args.api_base_url,
            "/invoices/full-mock-pipeline",
            {
                "tenant_id": tenant_id,
                "source": "upload",
                "file_url": "mock://incoming/seed-demo-invoice.pdf",
                "metadata": {
                    "sender_email": "ap@example.com",
                    "original_filename": "seed-demo-invoice.pdf",
                    "mime_type": "application/pdf",
                },
                "content": (
                    "invoice_number=INV-SEED-DEMO supplier_tax_id=TAX-12345 "
                    "subtotal=1000 tax_total=170 grand_total=1170 currency=USD "
                    "invoice_date=2026-05-07 po_number=PO-100"
                ),
            },
            headers,
        )
        invoice_id = pipeline["invoice"]["invoice_id"] if pipeline.get("invoice") else None
        workflow_status = pipeline["workflow_status"]

    print(
        json.dumps(
            {
                "status": "seeded",
                "api_base_url": args.api_base_url,
                "tenant_id": tenant_id,
                "tenant_slug": registered["tenant"]["slug"],
                "owner_email": args.email,
                "demo_password": args.password,
                "invoice_id": invoice_id,
                "workflow_status": workflow_status,
                "note": "Access token was not printed. Rotate demo credentials before shared use.",
            },
            indent=2,
        )
    )
    return 0


def post(base_url: str, path: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    return request(base_url, "POST", path, payload, headers)


def request(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"content-type": "application/json"}
    request_headers.update(headers or {})
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {response_body}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
