from fastapi import APIRouter, Depends, HTTPException

from app.agents.data.invoice_extraction_agent import InvoiceExtractionAgent
from app.agents.data.invoice_ingestion_agent import InvoiceIngestionAgent
from app.api.dependencies import (
    get_invoice_extraction_agent,
    get_invoice_ingestion_agent,
    get_ocr_provider_factory,
    require_permission,
)
from app.core.config import settings
from app.core.schemas import CurrentUserContext, InvoiceExtractionInput, InvoiceIngestionInput, Permission
from app.integrations.ocr.factory import OCRProviderFactory

router = APIRouter()


@router.get("/providers")
def list_ocr_providers(
    include_status: bool = True,
    factory: OCRProviderFactory = Depends(get_ocr_provider_factory),
):
    if include_status:
        return factory.provider_statuses()
    return factory.available_providers()


@router.post("/test-provider")
def test_ocr_provider(
    provider_name: str = "mock",
    factory: OCRProviderFactory = Depends(get_ocr_provider_factory),
) -> dict:
    provider = factory.get_provider(provider_name)
    return provider.health_check()


@router.get("/test-provider")
def get_ocr_provider_health(
    provider_name: str = "mock",
    factory: OCRProviderFactory = Depends(get_ocr_provider_factory),
) -> dict:
    provider = factory.get_provider(provider_name)
    return provider.health_check()


@router.post("/extract")
def extract_with_ocr(
    payload: InvoiceIngestionInput,
    ingestion_agent: InvoiceIngestionAgent = Depends(get_invoice_ingestion_agent),
    extraction_agent: InvoiceExtractionAgent = Depends(get_invoice_extraction_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_PROCESS)),
) -> dict:
    if settings.auth_enabled and payload.tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
    raw = ingestion_agent.ingest(payload)
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=raw.tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
            correlation_id=payload.correlation_id,
        )
    )
    return {
        "raw_invoice": raw,
        "extraction": extraction,
        "ocr_result": extraction.ocr_result,
        "confidence_summary": extraction.confidence_summary,
    }
