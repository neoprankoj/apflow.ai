from app.core.config import Settings, settings
from app.core.schemas import OCRProviderName
from app.integrations.ocr.base import OCRAdapterProtocol
from app.integrations.ocr.cloud import (
    AWSTextractOCRAdapter,
    AzureDocumentIntelligenceOCRAdapter,
    GoogleDocumentAIOCRAdapter,
)
from app.integrations.ocr.mock import MockOCRProvider
from app.integrations.ocr.ocr_space import OCRSpaceOCRAdapter


class OCRProviderFactory:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings

    def available_providers(self) -> list[str]:
        return [provider.value for provider in OCRProviderName]

    def provider_statuses(self) -> list[dict]:
        statuses = []
        for provider_name in OCRProviderName:
            provider = self.get_provider(provider_name.value)
            health = provider.health_check()
            statuses.append(
                {
                    "provider": provider_name.value,
                    "configured": bool(health.get("configured")),
                    "status": health.get("status", "unknown"),
                    "selected": provider_name.value == self.settings.ocr_provider,
                    "metadata": {key: value for key, value in health.items() if key not in {"provider", "configured", "status"}},
                }
            )
        return statuses

    def get_provider(self, provider_name: str | None = None) -> OCRAdapterProtocol:
        selected = OCRProviderName(provider_name or self.settings.ocr_provider)
        if selected == OCRProviderName.MOCK:
            return MockOCRProvider()
        if selected == OCRProviderName.AZURE:
            return AzureDocumentIntelligenceOCRAdapter(self.settings)
        if selected == OCRProviderName.GOOGLE:
            return GoogleDocumentAIOCRAdapter(self.settings)
        if selected == OCRProviderName.AWS:
            return AWSTextractOCRAdapter(self.settings)
        if selected == OCRProviderName.OCR_SPACE:
            return OCRSpaceOCRAdapter(self.settings)
        raise ValueError(f"unsupported OCR provider: {selected}")
