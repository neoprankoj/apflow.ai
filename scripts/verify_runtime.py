"""Runtime smoke test for a running APFlow AI stack.

Works against localhost Docker or a remote staging deployment:

    python scripts/verify_runtime.py --api-url https://api.example.com --web-url https://app.example.com
    python scripts/verify_runtime.py --api-url https://api.example.com --web-url https://app.example.com --auth-enabled --email owner@example.com --password '...'
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from uuid import UUID, uuid4

VALID_UPLOAD_WORKFLOW_STATUSES = {"approval_ready", "auto_approved", "review_required", "needs_review"}


@dataclass
class RuntimeContext:
    api_url: str
    web_url: str
    tenant_id: str
    token: str | None = None

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}


def main() -> int:
    args = parse_args()
    context = RuntimeContext(
        api_url=args.api_url.rstrip("/"),
        web_url=args.web_url.rstrip("/"),
        tenant_id=args.tenant_id,
    )

    health = get(context, "/health")
    ready = get(context, "/ready")
    dashboard = text(context.web_url)
    assert health["status"] == "ok"
    assert ready["status"] == "ready"
    assert "APFlow AI" in dashboard

    if ready.get("auth_enabled") or args.auth_enabled:
        context.token = resolve_token(context, args)

    if args.demo_reset:
        reset = post(context, "/admin/demo/reset", None)
        assert reset["workflow_status"] in VALID_UPLOAD_WORKFLOW_STATUSES

    verify_mock_pipeline_flow(context)
    uploaded = None
    if not args.skip_upload:
        uploaded = verify_upload_process_export_vendor_flow(context, skip_vendor=args.skip_vendor)

    if uploaded is not None:
        assert uploaded["workflow_status"] in VALID_UPLOAD_WORKFLOW_STATUSES
        if uploaded["workflow_status"] in {"approval_ready", "auto_approved"}:
            assert uploaded["erp_status"] == "success"
        if not args.skip_vendor:
            assert uploaded["vendor_status"] in {"under_review", "approved", "scheduled_for_payment", "paid", "received"}
    print("runtime verification passed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a running APFlow AI runtime")
    parser.add_argument("--api-url", default=os.getenv("APFLOW_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--web-url", default=os.getenv("APFLOW_WEB_BASE_URL", "http://127.0.0.1:3000"))
    parser.add_argument("--tenant-id", default=os.getenv("APFLOW_DEMO_TENANT_ID", "11111111-1111-1111-1111-111111111111"))
    parser.add_argument("--auth", dest="auth_enabled", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--auth-enabled", action="store_true", help="Force authenticated verification")
    parser.add_argument("--email", default=os.getenv("APFLOW_VERIFY_EMAIL", "demo-owner@apflow.local"))
    parser.add_argument("--password", default=os.getenv("APFLOW_VERIFY_PASSWORD", "demo-password-123"))
    parser.add_argument("--tenant-name", default=os.getenv("APFLOW_VERIFY_TENANT_NAME", "APFlow Runtime Tenant"))
    parser.add_argument("--tenant-slug", default=os.getenv("APFLOW_VERIFY_TENANT_SLUG", f"runtime-{uuid4().hex[:8]}"))
    parser.add_argument("--token", default=os.getenv("APFLOW_VERIFY_TOKEN"))
    parser.add_argument("--skip-upload", action="store_true", help="Skip invoice document upload/process checks")
    parser.add_argument("--skip-vendor", action="store_true", help="Skip vendor portal checks")
    parser.add_argument("--demo-reset", action="store_true", help="Verify staging-only /admin/demo/reset")
    return parser.parse_args()


def resolve_token(context: RuntimeContext, args: argparse.Namespace) -> str:
    if args.token:
        return args.token
    try:
        logged_in = post(
            context,
            "/auth/login",
            {
                "email": args.email,
                "password": args.password,
                "tenant_id": args.tenant_id,
            },
        )
        context.tenant_id = logged_in["tenant"]["id"]
        return logged_in["access_token"]
    except RuntimeError:
        pass
    try:
        logged_in = post(
            context,
            "/auth/login",
            {
                "email": args.email,
                "password": args.password,
            },
        )
        context.tenant_id = logged_in["tenant"]["id"]
        return logged_in["access_token"]
    except RuntimeError:
        pass
    registered = post(
        context,
        "/auth/register-demo-tenant",
        {
            "tenant_name": args.tenant_name,
            "tenant_slug": args.tenant_slug,
            "email": args.email,
            "full_name": "Runtime Owner",
            "password": args.password,
        },
    )
    context.tenant_id = registered["tenant"]["id"]
    return registered["access_token"]


def verify_mock_pipeline_flow(context: RuntimeContext) -> None:
    invoice_number = f"INV-RUNTIME-{uuid4().hex[:8]}"
    post(context, "/erp/sync-vendors", {"tenant_id": context.tenant_id, "adapter_type": "priority"})
    post(context, "/erp/sync-purchase-orders", {"tenant_id": context.tenant_id, "adapter_type": "priority"})
    pipeline = post(
        context,
        "/invoices/full-mock-pipeline",
        {
            "tenant_id": context.tenant_id,
            "source": "upload",
            "file_url": "mock://incoming/runtime-invoice.pdf",
            "metadata": {
                "sender_email": "ap@example.com",
                "original_filename": "runtime-invoice.pdf",
                "mime_type": "application/pdf",
            },
            "content": (
                f"invoice_number={invoice_number} "
                "supplier_tax_id=TAX-12345 subtotal=1000 tax_total=170 grand_total=1170 "
                "currency=USD invoice_date=2026-05-07 po_number=PO-100"
            ),
        },
    )
    invoice_id = pipeline["invoice"]["invoice_id"]
    export = post(
        context,
        "/erp/export-invoice",
        {"tenant_id": context.tenant_id, "adapter_type": "priority", "invoice_id": invoice_id},
    )
    invoices = get(context, f"/invoices?tenant_id={context.tenant_id}")
    vendor_id = next(item["vendor_id"] for item in invoices if item["invoice_id"] == invoice_id)
    assert vendor_id, "runtime invoice was not linked to a vendor"
    access = post(
        context,
        "/vendor/access",
        {"tenant_id": context.tenant_id, "vendor_id": vendor_id, "email": "vendor@example.com"},
    )
    token = access["access_token"]
    vendor_invoices = get(
        context,
        f"/vendor/invoices?tenant_id={context.tenant_id}&access_token={urllib.parse.quote(token)}",
    )
    message = post(
        context,
        f"/vendor/messages?access_token={urllib.parse.quote(token)}",
        {
            "tenant_id": context.tenant_id,
            "invoice_id": invoice_id,
            "sender_email": "vendor@example.com",
            "message": "Please confirm payment timing.",
        },
    )
    chat = post(
        context,
        f"/vendor/chat?access_token={urllib.parse.quote(token)}",
        {
            "tenant_id": context.tenant_id,
            "invoice_id": invoice_id,
            "question": "What is the payment status?",
        },
    )

    assert UUID(invoice_id)
    assert export["status"] == "success"
    assert any(item["invoice_id"] == invoice_id for item in vendor_invoices)
    assert message["status"] == "submitted"
    assert chat["intent"] == "payment_status"


def verify_upload_process_export_vendor_flow(context: RuntimeContext, skip_vendor: bool = False) -> dict:
    tenant_id = context.tenant_id if context.token else str(uuid4())
    invoice_number = f"INV-RUNTIME-UPLOAD-{uuid4().hex[:8]}"
    invoice_bytes = (
        f"invoice_number={invoice_number} supplier_name=Northstar supplier_tax_id=TAX-12345 "
        "subtotal=1000 tax_total=170 grand_total=1170 currency=USD "
        "invoice_date=2026-05-07 po_number=PO-100"
    ).encode("utf-8")
    upload = multipart_post(
        context,
        "/documents/invoices/upload",
        {"tenant_id": tenant_id},
        "file",
        "runtime-invoice.pdf",
        "application/pdf",
        invoice_bytes,
    )
    document_id = upload["document"]["document_id"]
    extract = post(context, f"/documents/invoices/{document_id}/extract?tenant_id={tenant_id}", None)
    process = post(context, f"/documents/invoices/{document_id}/process", {"tenant_id": tenant_id})
    if process["workflow_status"] in {"review_required", "needs_review"}:
        return {
            "review_status": extract["review_status"],
            "workflow_status": process["workflow_status"],
            "erp_status": "skipped",
            "vendor_status": "under_review",
        }
    invoice_id = process["pipeline_result"]["invoice"]["invoice_id"]
    export = post(
        context,
        "/erp/export-invoice",
        {"tenant_id": tenant_id, "adapter_type": "priority", "invoice_id": invoice_id},
    )
    if skip_vendor:
        return {
            "review_status": extract["review_status"],
            "workflow_status": process["workflow_status"],
            "erp_status": export["status"],
            "vendor_status": "skipped",
        }
    access = post(context, "/vendor/access", {"tenant_id": tenant_id, "email": "runtime-vendor@example.com"})
    vendor = get(
        context,
        f"/vendor/invoices/{invoice_id}?tenant_id={tenant_id}&access_token={urllib.parse.quote(access['access_token'])}",
    )
    return {
        "review_status": extract["review_status"],
        "workflow_status": process["workflow_status"],
        "erp_status": export["status"],
        "vendor_status": vendor["status"],
    }


def get(context: RuntimeContext, path: str):
    return request(context, "GET", path)


def post(context: RuntimeContext, path: str, payload: dict | None):
    return request(context, "POST", path, payload)


def request(context: RuntimeContext, method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"content-type": "application/json"}
    headers.update(context.auth_headers)
    req = urllib.request.Request(
        f"{context.api_url}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {body}") from exc


def multipart_post(
    context: RuntimeContext,
    path: str,
    fields: dict[str, str],
    file_field: str,
    file_name: str,
    content_type: str,
    content: bytes,
):
    boundary = f"----apflow{uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    headers = {"content-type": f"multipart/form-data; boundary={boundary}"}
    headers.update(context.auth_headers)
    req = urllib.request.Request(
        f"{context.api_url}{path}",
        data=b"".join(chunks),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"POST {path} failed: {exc.code} {body}") from exc


def text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
