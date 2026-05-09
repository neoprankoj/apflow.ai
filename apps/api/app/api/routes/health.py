from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
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
