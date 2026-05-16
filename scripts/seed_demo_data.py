"""Seed predictable APFlow demo states through the running API.

The script does not print tokens or secrets. Live OCR providers are never
invoked during explicit seed modes; staging reset seed modes create deterministic
records directly on the backend.
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
    parser.add_argument("--tenant-id")
    parser.add_argument("--email", default="demo-owner@apflow.local")
    parser.add_argument("--password", default="demo-password-123")
    parser.add_argument("--adapter", default="priority")
    parser.add_argument(
        "--mode",
        choices=("clean", "approval-ready", "review-required", "vendor-preview", "inbox-demo", "all"),
        default="approval-ready",
    )
    args = parser.parse_args()

    registered = authenticate(args)
    token = registered["access_token"]
    tenant_id = registered["tenant"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    post(args.api_base_url, "/erp/sync-vendors", {"tenant_id": tenant_id, "adapter_type": args.adapter}, headers)
    post(args.api_base_url, "/erp/sync-purchase-orders", {"tenant_id": tenant_id, "adapter_type": args.adapter}, headers)

    reset_mode = backend_seed_mode(args.mode)
    reset = post(args.api_base_url, f"/admin/demo/reset?seed_mode={reset_mode}", None, headers)
    vendor_access_created = False
    if args.mode == "vendor-preview":
        seeded_invoices = get(args.api_base_url, f"/invoices?tenant_id={tenant_id}", headers)
        seeded_vendor_id = next(
            (record["vendor_id"] for record in seeded_invoices if record["invoice_id"] == reset.get("invoice_id")),
            None,
        )
        post(
            args.api_base_url,
            "/vendor/access",
            {
                "tenant_id": tenant_id,
                "email": "demo-vendor@apflow.local",
                "vendor_id": seeded_vendor_id,
            },
            headers,
        )
        vendor_access_created = True

    print(
        json.dumps(
            {
                "status": "seeded",
                "api_base_url": args.api_base_url,
                "tenant_id": tenant_id,
                "tenant_slug": registered["tenant"]["slug"],
                "owner_email": args.email,
                "demo_password": args.password,
                "mode": args.mode,
                "invoice_id": reset.get("invoice_id"),
                "workflow_status": reset["workflow_status"],
                "vendor_access_created": vendor_access_created,
                "note": "Access token was not printed. Rotate demo credentials before shared use.",
            },
            indent=2,
        )
    )
    return 0


def backend_seed_mode(mode: str) -> str:
    if mode == "vendor-preview":
        return "approval_ready"
    return mode.replace("-", "_")


def authenticate(args: argparse.Namespace) -> dict:
    if args.tenant_id:
        try:
            return post(
                args.api_base_url,
                "/auth/login",
                {
                    "email": args.email,
                    "password": args.password,
                    "tenant_id": args.tenant_id,
                },
            )
        except RuntimeError:
            pass
    return post(
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


def post(base_url: str, path: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    return request(base_url, "POST", path, payload, headers)


def get(base_url: str, path: str, headers: dict[str, str] | None = None) -> dict:
    return request(base_url, "GET", path, None, headers)


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
