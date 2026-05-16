from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_demo_data", Path(__file__).with_name("seed_demo_data.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_backend_seed_mode_mapping():
    module = load_seed_module()

    assert module.backend_seed_mode("clean") == "clean"
    assert module.backend_seed_mode("approval-ready") == "approval_ready"
    assert module.backend_seed_mode("review-required") == "review_required"
    assert module.backend_seed_mode("vendor-preview") == "approval_ready"
    assert module.backend_seed_mode("inbox-demo") == "inbox_demo"
    assert module.backend_seed_mode("all") == "all"


def test_authenticate_prefers_existing_tenant_when_requested():
    module = load_seed_module()
    calls = []

    def fake_post(base_url, path, payload, headers=None):
        calls.append((path, payload))
        return {
            "access_token": "token",
            "tenant": {"id": payload["tenant_id"], "slug": "demo"},
        }

    module.post = fake_post
    args = type(
        "Args",
        (),
        {
            "api_base_url": "http://api.local",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "email": "demo-owner@apflow.local",
            "password": "demo-password-123",
            "tenant_name": "APFlow Demo Tenant",
            "tenant_slug": "apflow-demo",
        },
    )()

    authenticated = module.authenticate(args)

    assert authenticated["tenant"]["id"] == args.tenant_id
    assert calls == [
        (
            "/auth/login",
            {
                "email": "demo-owner@apflow.local",
                "password": "demo-password-123",
                "tenant_id": "11111111-1111-1111-1111-111111111111",
            },
        )
    ]


def test_demo_expected_json_files_are_valid():
    expected_dir = Path(__file__).parents[1] / "samples" / "demo" / "expected"

    for path in expected_dir.glob("*.json"):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        assert "scenario" in payload
