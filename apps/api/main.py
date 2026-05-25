import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.auth import router as auth_router
from app.api.routes.demo_admin import router as demo_admin_router
from app.api.routes.documents import router as documents_router
from app.api.routes.erp import router as erp_router
from app.api.routes.health import router as health_router
from app.api.routes.invoices import router as invoices_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.ocr import router as ocr_router
from app.api.routes.payments import router as payments_router
from app.api.routes.review import router as review_router
from app.api.routes.vendor import router as vendor_router
from app.api.routes.workflows import router as workflows_router
from app.core.config import settings

logger = logging.getLogger("apflow.startup")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        (
            "APFlow AI startup: env=%s repository_mode=%s auth_enabled=%s demo_mode=%s "
            "ocr_provider=%s storage_provider=%s erp_adapters=%s public_app_url=%s api_public_url=%s"
        ),
        settings.app_env,
        "in_memory" if settings.use_in_memory_repositories else "sqlalchemy",
        settings.auth_enabled,
        settings.demo_mode,
        settings.ocr_provider,
        settings.document_storage_provider,
        ["priority", "odoo", "zoho_books"],
        settings.public_app_url,
        settings.api_public_url,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="APFlow AI API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Vendor-Access-Token"],
    )
    app.include_router(health_router)
    app.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
    app.include_router(demo_admin_router, prefix="/admin", tags=["admin"])
    app.include_router(erp_router, prefix="/erp", tags=["erp"])
    app.include_router(ocr_router, prefix="/ocr", tags=["ocr"])
    app.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
    app.include_router(payments_router, prefix="/payments", tags=["payments"])
    app.include_router(review_router, prefix="/review", tags=["review"])
    app.include_router(vendor_router, prefix="/vendor", tags=["vendor"])
    app.include_router(documents_router, prefix="/documents", tags=["documents"])
    app.include_router(invoices_router, prefix="/invoices", tags=["invoices"])
    app.include_router(workflows_router, prefix="/workflow", tags=["workflow"])

    return app


app = create_app()


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "ok"}
