from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.dependencies import require_permission
from app.core.config import settings
from app.core.schemas import Permission, ProductReadinessCheck, ProductReadinessLevel, ProductReadinessResponse
from app.db.session import SessionLocal
from app.integrations.ocr.factory import OCRProviderFactory
from app.integrations.erp.mock_adapters import MockOdooERPAdapter, MockPriorityERPAdapter, MockZohoBooksAdapter
from app.integrations.storage.mock import FileSystemStorageAdapter, InMemoryStorageAdapter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "checked_at": datetime.now(UTC).isoformat()}


@router.get("/ready")
def ready() -> dict:
    checks: dict[str, dict | str] = {
        "database": _database_check(),
        "ocr": _ocr_check(),
        "document_storage": _document_storage_check(),
        "erp_adapters": {
            "status": "ok",
            "priority_mode": settings.priority_erp_mode,
            "available": [
                MockPriorityERPAdapter().get_adapter_name(),
                MockOdooERPAdapter().get_adapter_name(),
                MockZohoBooksAdapter().get_adapter_name(),
            ],
        },
    }
    status = "ready" if all(check.get("status") == "ok" for check in checks.values()) else "not_ready"
    return {
        "status": status,
        "checked_at": datetime.now(UTC).isoformat(),
        "environment": settings.app_env,
        "repository_mode": "in_memory" if settings.use_in_memory_repositories else "sqlalchemy",
        "auth_enabled": settings.auth_enabled,
        "demo_mode": settings.demo_mode,
        "checks": checks,
    }


@router.get("/ready/product", response_model=ProductReadinessResponse)
def product_readiness(_context=Depends(require_permission(Permission.TENANT_ADMIN))) -> ProductReadinessResponse:
    checks = _product_readiness_checks()
    return ProductReadinessResponse(
        environment=settings.app_env,
        generated_at=datetime.now(UTC),
        demo_ready=_readiness_level(
            key="demo_ready",
            checks=checks,
            required_keys=[
                "database_connected",
                "document_storage_configured",
                "auth_enabled",
                "audit_trail_available",
                "invoice_upload_available",
                "human_review_available",
                "approval_inbox_available",
                "vendor_safe_preview_available",
                "mock_erp_export_available",
                "payment_status_foundation_available",
                "ocr_provider_configured",
                "priority_writes_disabled",
                "demo_readiness_pack_exists",
            ],
            summary_ready="APFlow is ready for controlled demos using mock ERP export and safe Priority dry-run/import flows.",
            summary_not_ready="APFlow needs one or more demo-critical checks before a controlled AP manager demo.",
        ),
        pilot_ready=_readiness_level(
            key="pilot_ready",
            checks=checks,
            required_keys=[
                "database_connected",
                "document_storage_configured",
                "auth_enabled",
                "tenant_rbac_enabled",
                "audit_trail_available",
                "invoice_upload_available",
                "human_review_available",
                "approval_inbox_available",
                "vendor_safe_preview_available",
                "ocr_provider_configured",
                "https_domain_configured",
                "production_access_hardening",
                "tenant_isolation_tests_documented",
                "vendor_safe_protections_documented",
                "production_vendor_access_ready",
                "payment_status_sync_ready",
                "notification_delivery_configured",
                "real_customer_erp_flow_ready",
            ],
            summary_ready="APFlow is ready for a controlled customer pilot with production-grade access, notifications, vendor lifecycle, and ERP posture.",
            summary_not_ready="Not ready yet. Before real customer pilots, finish production access hardening, vendor access lifecycle, payment status sync, notification delivery, and customer ERP mapping.",
        ),
        production_ready=_readiness_level(
            key="production_ready",
            checks=checks,
            required_keys=[
                "app_env_production",
                "demo_mode_disabled_for_production",
                "demo_reset_disabled_for_production",
                "auth_required_for_production",
                "jwt_secret_non_default",
                "auth_enabled",
                "https_domain_configured",
                "production_secret_policy_documented",
                "backup_runbook_documented",
                "public_ports_hardened",
                "production_vendor_access_ready",
                "payment_status_sync_ready",
                "real_notification_provider_configured",
                "billing_configured",
                "usage_metering_configured",
                "accuracy_analytics_ready",
                "einvoicing_compliance_ready",
            ],
            summary_ready="APFlow is production ready.",
            summary_not_ready="Not ready. Domain/HTTPS, production secrets, demo-mode blocking, billing/metering, vendor access, and production security controls are still required.",
        ),
        checks=checks,
        message="Readiness does not enable production. It only shows what is safe to claim.",
    )


def _database_check() -> dict[str, str]:
    if settings.use_in_memory_repositories:
        return {"status": "ok", "mode": "in_memory"}
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "mode": "sqlalchemy"}
    except Exception as exc:
        return {"status": "failed", "mode": "sqlalchemy", "error": exc.__class__.__name__}


def _ocr_check() -> dict[str, str]:
    try:
        provider = OCRProviderFactory().get_provider(settings.ocr_provider)
        result = provider.health_check()
        provider_status = result["status"]
        return {
            "status": "ok" if provider_status == "ok" else "degraded",
            "provider": provider.get_provider_name(),
            "provider_status": provider_status,
        }
    except Exception as exc:
        return {"status": "failed", "provider": settings.ocr_provider, "error": exc.__class__.__name__}


def _product_readiness_checks() -> list[ProductReadinessCheck]:
    database = _database_check()
    storage = _document_storage_check()
    ocr = _ocr_check()
    priority_mode = (settings.priority_erp_mode or "mock").lower()
    priority_writes_enabled = bool(settings.priority_erp_enable_writes)
    read_only_fetch_enabled = bool(settings.priority_erp_read_only_fetch_enabled)
    https_configured = _uses_https(settings.public_app_url) and _uses_https(settings.api_public_url)
    auth_secret_strong = _auth_secret_is_strong()

    return [
        _check(
            "database_connected",
            "Database connected",
            "pass" if database.get("status") == "ok" else "fail",
            "operations",
            "Database readiness check is healthy." if database.get("status") == "ok" else "Database readiness check failed.",
            "Inspect database container, credentials, and migrations.",
            database.get("mode"),
        ),
        _check(
            "document_storage_configured",
            "Document storage configured",
            "pass" if storage.get("status") == "ok" else "fail",
            "operations",
            "Uploaded invoice document storage is available."
            if storage.get("status") == "ok"
            else "Document storage is not ready.",
            "Check DOCUMENT_STORAGE_PROVIDER and storage mount/volume health.",
            str(storage.get("provider")),
        ),
        _check(
            "auth_enabled",
            "Auth enabled",
            "pass" if settings.auth_enabled else "fail",
            "security",
            "JWT auth is enabled." if settings.auth_enabled else "Auth is disabled.",
            "Enable AUTH_ENABLED before pilot or production access.",
        ),
        _check(
            "tenant_rbac_enabled",
            "Tenant RBAC enabled",
            "pass" if settings.auth_enabled else "fail",
            "security",
            "Tenant membership and role permissions are enforced when auth is enabled."
            if settings.auth_enabled
            else "Tenant RBAC is not enforced while auth is disabled.",
            "Keep auth enabled and verify tenant role permissions.",
        ),
        _check(
            "audit_trail_available",
            "Audit Trail available",
            "pass",
            "demo",
            "Audit Trail is available for approval, export, review, and import proof.",
        ),
        _check(
            "runtime_verifier_documented",
            "Runtime verifier documented",
            "pass",
            "operations",
            "Runtime verification commands are documented in the runbook.",
        ),
        _check(
            "demo_mode_enabled",
            "Demo mode enabled",
            "pass" if settings.demo_mode else "warning",
            "demo",
            "Demo mode is enabled for private staging demos."
            if settings.demo_mode
            else "Demo mode is disabled; use a real tenant login.",
        ),
        _check(
            "demo_login_available",
            "Demo login available",
            "pass" if settings.demo_mode else "warning",
            "demo",
            "Demo Login is available for private staging."
            if settings.demo_mode
            else "Demo Login may be unavailable when demo mode is disabled.",
        ),
        _check(
            "demo_reset_disabled_or_guarded",
            "Demo reset guarded",
            "pass" if not settings.allow_demo_reset or settings.app_env == "staging" else "fail",
            "demo",
            "Demo reset is disabled or restricted to staging."
            if not settings.allow_demo_reset or settings.app_env == "staging"
            else "Demo reset is enabled outside staging.",
            "Keep ALLOW_DEMO_RESET=false except during controlled private staging cleanup.",
        ),
        _check(
            "demo_readiness_pack_exists",
            "Demo readiness pack exists",
            "pass",
            "demo",
            "Demo readiness, walkthrough, safety, and troubleshooting docs are available.",
        ),
        _check(
            "sample_data_seed_available",
            "Sample data seed available",
            "pass",
            "demo",
            "Seed modes exist for clean, approval-ready, review-required, vendor-preview, all, and inbox-demo flows.",
        ),
        _check(
            "ocr_provider_configured",
            "OCR provider configured",
            "pass" if ocr.get("status") == "ok" else "fail",
            "integrations",
            f"Selected OCR provider `{ocr.get('provider')}` is ready."
            if ocr.get("status") == "ok"
            else f"Selected OCR provider `{ocr.get('provider')}` is not ready.",
            "Check OCR provider credentials and /ocr/test-provider.",
            str(ocr.get("provider_status")),
        ),
        _check(
            "ocr_space_engine_configured",
            "OCR.space engine configured",
            "pass" if settings.ocr_provider != "ocr_space" or bool(settings.ocr_space_engine) else "fail",
            "integrations",
            "OCR.space engine is configured." if settings.ocr_provider == "ocr_space" else "OCR.space is not the selected provider.",
            "Set OCR_SPACE_ENGINE; engine 2 is currently recommended on staging.",
            f"engine {settings.ocr_space_engine}" if settings.ocr_provider == "ocr_space" else None,
        ),
        _check(
            "ocr_fallback_configured",
            "OCR fallback configured",
            "pass" if settings.ocr_provider != "ocr_space" or settings.ocr_space_enable_engine_fallback else "warning",
            "integrations",
            "OCR.space fallback is enabled."
            if settings.ocr_provider == "ocr_space" and settings.ocr_space_enable_engine_fallback
            else "OCR fallback is disabled or not applicable.",
            "Keep OCR_SPACE_ENABLE_ENGINE_FALLBACK=true for staging OCR.space demos.",
        ),
        _check(
            "invalid_file_diagnostics_enabled",
            "Invalid file diagnostics enabled",
            "pass",
            "integrations",
            "Invalid PDF/PNG/JPG file signatures are diagnosed before OCR provider calls.",
        ),
        _check("invoice_upload_available", "Invoice upload available", "pass", "demo", "Invoice upload and processing routes are available."),
        _check("human_review_available", "Human review available", "pass", "demo", "Human review and correction workflow is available."),
        _check("approval_inbox_available", "Approval Inbox available", "pass", "demo", "Approval Inbox supports approve, reject, and hold decisions."),
        _check("vendor_safe_preview_available", "Vendor-safe preview available", "pass", "demo", "Vendor-safe preview hides internal risk and audit details."),
        _check("mock_erp_export_available", "Mock ERP export available", "pass", "demo", "Mock ERP export is available for safe demos."),
        _check(
            "payment_status_foundation_available",
            "Payment status foundation available",
            "pass",
            "demo",
            "APFlow can track tenant-scoped manual/mock payment statuses and show vendor-safe payment messages.",
            "Real ERP payment sync remains a future pilot requirement.",
        ),
        _check(
            "priority_mode_status",
            "Priority mode status",
            "pass" if priority_mode == "mock" else "warning",
            "integrations",
            f"Priority is running in `{priority_mode}` mode.",
            "Keep Priority mode mock for staging demos unless real read-only testing is planned.",
            f"read-only fetch {'enabled' if read_only_fetch_enabled else 'disabled'}",
        ),
        _check(
            "priority_writes_disabled",
            "Priority writes disabled",
            "pass" if not priority_writes_enabled else "fail",
            "integrations",
            "Priority writes are disabled."
            if not priority_writes_enabled
            else "Priority writes are enabled.",
            "Keep PRIORITY_ERP_ENABLE_WRITES=false until real write mapping and production controls are approved.",
        ),
        _check("priority_mapping_admin_available", "Priority Mapping Admin available", "pass", "integrations", "Priority mapping admin UI/API is available."),
        _check("priority_readiness_drill_available", "Priority readiness drill available", "pass", "integrations", "Priority real-readiness drill is available and gated."),
        _check("priority_real_readonly_fetch_gated", "Priority read-only fetch gated", "pass", "integrations", "Real Priority fetch is explicit, limited, and GET-only when enabled."),
        _check("priority_live_write_not_enabled", "Priority live writes not enabled", "pass" if not priority_writes_enabled else "fail", "integrations", "No live Priority writes are enabled."),
        _check("production_access_hardening", "Production access hardening", "fail", "security", "Production access hardening is not complete.", "Finish domain/HTTPS, secret rotation, public port restrictions, tenant access review, and incident procedures."),
        _check("tenant_isolation_tests_documented", "Tenant isolation guardrails", "pass", "security", "Tenant-scoped protected endpoints deny or filter cross-tenant data.", "Keep tenant isolation tests in the release gate."),
        _check("vendor_safe_protections_documented", "Vendor-safe data boundary", "pass", "security", "Vendor-facing responses use an allowlist and hide internal risk, audit, ERP, and token metadata.", "Keep vendor-safe leak tests in the release gate."),
        _check("vendor_access_lifecycle_available", "Vendor access lifecycle available", "pass", "security", "Vendor access can be created, listed, revoked, rotated, expired, and audited.", "Add real notification delivery before using this for external supplier invitations."),
        _check("vendor_access_token_hashing_available", "Vendor access token hashing", "pass", "security", "Vendor access tokens are stored as hashes and raw tokens are shown only once.", "Keep token hashes and raw tokens out of logs and support tickets."),
        _check("vendor_access_expiry_revocation_available", "Vendor access expiry and revocation", "pass", "security", "Expired and revoked vendor access tokens are denied.", "Set short expirations for pilot supplier access."),
        _check("real_vendor_notification_delivery", "Vendor notification delivery", "fail", "pilot", "Real vendor invite email delivery is not configured.", "Add provider-backed invitation delivery before live supplier onboarding."),
        _check(
            "real_payment_sync_configured",
            "Real payment sync configured",
            "fail",
            "pilot",
            "Manual/mock payment status tracking exists, but real ERP payment sync is not configured.",
            "Connect read-only ERP payment status sync before pilot/production commitments.",
        ),
        _check("payment_status_sync_ready", "Payment status sync", "fail", "pilot", "Real payment status sync is missing.", "Add ERP/payment status sync before pilot/production commitments."),
        _check("vendor_payment_chatbot_available", "Vendor payment-status chatbot", "pass", "pilot", "A deterministic vendor-safe payment-status chatbot foundation is available.", "Add abuse controls, escalation ownership, and real notification handoff before live supplier rollout."),
        _check("vendor_chatbot_missing", "Vendor chatbot production hardening", "warning", "pilot", "Vendor chatbot foundation exists, but production support escalation and abuse controls are not complete.", "Define production escalation, abuse controls, and support ownership."),
        _check("notification_delivery_abstraction_available", "Notification delivery abstraction", "pass", "pilot", "Mock notification delivery and provider readiness checks are available.", "Connect a real provider before live external communication."),
        _check("mock_notification_provider_available", "Mock notification provider", "pass", "pilot", "Mock notifications can be recorded inside APFlow without external sends."),
        _check("real_email_provider_configured", "Real email provider configured", "fail", "pilot", "Email notification provider is not configured.", "Configure and test a real email provider before live supplier/approver notifications."),
        _check("real_slack_provider_configured", "Real Slack provider configured", "warning", "pilot", "Slack notification provider is not configured.", "Configure only if Slack delivery is needed for a pilot."),
        _check("real_teams_provider_configured", "Real Teams provider configured", "warning", "pilot", "Teams notification provider is not configured.", "Configure only if Teams delivery is needed for a pilot."),
        _check("notification_delivery_configured", "Notification delivery configured", "fail", "pilot", "Notification abstraction exists, but real email/Slack/Teams delivery is not configured.", "Configure and test a real notification provider for pilots."),
        _check("app_env_production", "Production environment", "pass" if settings.app_env == "production" else "fail", "production", f"Current APP_ENV is `{settings.app_env}`.", "Deploy with APP_ENV=production only after production controls are complete."),
        _check("demo_mode_disabled_for_production", "Demo mode disabled for production", "pass" if not settings.demo_mode else "fail", "production", "Demo mode is disabled." if not settings.demo_mode else "Demo mode is enabled.", "Disable DEMO_MODE before production."),
        _check("demo_reset_disabled_for_production", "Demo reset disabled for production", "pass" if not settings.allow_demo_reset else "fail", "production", "Demo reset is disabled." if not settings.allow_demo_reset else "Demo reset is enabled.", "Keep ALLOW_DEMO_RESET=false outside controlled private staging cleanup."),
        _check("auth_required_for_production", "Auth required for production", "pass" if settings.auth_enabled else "fail", "production", "Auth is enabled." if settings.auth_enabled else "Auth is disabled.", "Set AUTH_ENABLED=true before pilot or production access."),
        _check("jwt_secret_non_default", "JWT secret non-default", "pass" if auth_secret_strong else "fail", "security", "JWT signing secret is configured with a non-default value." if auth_secret_strong else "JWT signing secret is default, empty, or too short.", "Set AUTH_SECRET_KEY to a strong server-only secret."),
        _check("https_domain_configured", "Domain and HTTPS configured", "pass" if https_configured else "fail", "production", "Public app/API URLs use HTTPS." if https_configured else "Domain and HTTPS are not configured.", "Configure domain, HTTPS, and CORS when access/security hardening is ready."),
        _check("production_secret_policy_documented", "Production secret policy documented", "pass", "security", "Security docs cover secret handling and rotation reminders."),
        _check("backup_runbook_documented", "Backup runbook documented", "pass", "operations", "Staging backup/restore operations are documented."),
        _check("public_ports_hardened", "Public ports hardened", "fail", "security", "Production public port hardening is not complete.", "Restrict database/cache/object storage ports before production."),
        _check("production_vendor_access_ready", "Production vendor access ready", "warning", "production", "Vendor access lifecycle foundation exists, but live invitation delivery and support operations are still incomplete.", "Configure email delivery, domain/HTTPS, support ownership, and monitoring before production supplier access."),
        _check("real_notification_provider_configured", "Real notification provider configured", "fail", "production", "No production notification provider is configured.", "Configure SendGrid/Postmark/Slack/Teams or equivalent."),
        _check("real_customer_erp_flow_ready", "Real customer ERP flow ready", "fail", "integrations", "Real customer Priority write flow is not live.", "Complete customer-specific mapping, read-only verification, write approval, and rollback plan."),
        _check("billing_configured", "Billing configured", "fail", "production", "Billing is not configured.", "Add commercial billing before production SaaS launch."),
        _check("usage_metering_configured", "Usage metering configured", "fail", "commercial", "Usage metering is missing.", "Add tenant usage metering for invoices, OCR, storage, and ERP sync."),
        _check("accuracy_analytics_ready", "Accuracy analytics ready", "fail", "commercial", "OCR/review accuracy analytics are missing.", "Track extraction accuracy, correction rates, and review outcomes."),
        _check("einvoicing_compliance_ready", "E-invoicing compliance ready", "fail", "commercial", "E-invoicing compliance is not complete.", "Define regional e-invoicing and tax compliance requirements."),
    ]


def _check(
    key: str,
    label: str,
    status: str,
    category: str,
    message: str,
    next_step: str | None = None,
    safe_detail: str | None = None,
) -> ProductReadinessCheck:
    return ProductReadinessCheck(
        key=key,
        label=label,
        status=status,
        category=category,
        message=message,
        next_step=next_step,
        safe_detail=safe_detail,
    )


def _readiness_level(
    key: str,
    checks: list[ProductReadinessCheck],
    required_keys: list[str],
    summary_ready: str,
    summary_not_ready: str,
) -> ProductReadinessLevel:
    by_key = {check.key: check for check in checks}
    blockers = [
        by_key[item].label
        for item in required_keys
        if item in by_key and by_key[item].status == "fail"
    ]
    warnings = [
        by_key[item].label
        for item in required_keys
        if item in by_key and by_key[item].status == "warning"
    ]
    if blockers:
        status = "not_ready"
        summary = summary_not_ready
    elif warnings:
        status = "partially_ready"
        summary = summary_ready
    else:
        status = "ready"
        summary = summary_ready
    return ProductReadinessLevel(
        key=key,
        status=status,
        summary=summary,
        blockers=blockers,
        warnings=warnings,
    )


def _uses_https(value: str) -> bool:
    return value.lower().startswith("https://")


def _auth_secret_is_strong() -> bool:
    return settings.auth_secret_key not in {"", "dev-only-change-me-32-byte-minimum-key"} and len(settings.auth_secret_key) >= 32


def _document_storage_check() -> dict[str, str | bool]:
    try:
        adapter = (
            FileSystemStorageAdapter(settings.document_storage_path)
            if settings.document_storage_provider == "filesystem"
            else InMemoryStorageAdapter()
        )
        result = adapter.health_check()
        return {
            "status": result["status"],
            "provider": adapter.get_provider_name(),
            "configured": result["configured"],
        }
    except Exception as exc:
        return {
            "status": "failed",
            "provider": settings.document_storage_provider,
            "configured": False,
            "error": exc.__class__.__name__,
        }
