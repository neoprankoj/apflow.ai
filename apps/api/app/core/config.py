from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "APFlow AI"
    app_env: Literal["local", "staging", "production"] = "local"
    public_app_url: str = "http://127.0.0.1:3000"
    api_public_url: str = "http://127.0.0.1:8000"
    cors_allowed_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    database_url: str = "postgresql+psycopg://apflow:apflow@localhost:5432/apflow"
    use_in_memory_repositories: bool = True
    testing: bool = False
    postgres_password: str = "apflow"
    redis_url: str = "redis://localhost:6379/0"
    object_storage_endpoint: str = "http://localhost:9000"
    object_storage_bucket: str = "apflow-invoices"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    document_storage_provider: str = "memory"
    document_storage_path: str = ".storage/documents"
    max_invoice_upload_bytes: int = 10 * 1024 * 1024
    ocr_provider: str = "mock"
    ocr_space_api_key: str = ""
    ocr_space_api_url: str = "https://api.ocr.space/parse/image"
    ocr_space_language: str = "eng"
    ocr_space_engine: str = "2"
    ocr_space_timeout_seconds: int = 60
    azure_document_intelligence_endpoint: str = ""
    azure_document_intelligence_key: str = ""
    google_document_ai_project_id: str = ""
    google_document_ai_location: str = ""
    google_document_ai_processor_id: str = ""
    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    erp_provider: str = "mock"
    priority_erp_mode: Literal["mock", "real"] = "mock"
    priority_erp_base_url: str = ""
    priority_erp_company: str = ""
    priority_erp_environment: str = ""
    priority_erp_username: str = ""
    priority_erp_password: str = ""
    priority_erp_api_key: str = ""
    priority_erp_timeout_seconds: int = 15
    priority_erp_verify_tls: bool = True
    priority_erp_enable_writes: bool = False
    priority_erp_vendors_entity_name: str = ""
    priority_erp_purchase_orders_entity_name: str = ""
    priority_erp_invoices_entity_name: str = ""
    email_provider: str = "mock"
    auth_enabled: bool = False
    auth_secret_key: str = "dev-only-change-me-32-byte-minimum-key"
    access_token_expire_minutes: int = 60
    demo_mode: bool = True
    allow_demo_mode_in_production: bool = False
    allow_demo_reset: bool = False
    demo_tenant_id: str = "11111111-1111-1111-1111-111111111111"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_allowed_origins")
    @classmethod
    def normalize_cors_origins(cls, value: str) -> str:
        origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return ",".join(dict.fromkeys(origins))

    @property
    def cors_origins(self) -> list[str]:
        return [origin for origin in self.cors_allowed_origins.split(",") if origin]

    @model_validator(mode="after")
    def validate_runtime_safety(self) -> "Settings":
        if self.app_env not in {"staging", "production"}:
            return self

        if not self.database_url:
            raise ValueError("DATABASE_URL is required for staging and production")
        if not self.public_app_url:
            raise ValueError("PUBLIC_APP_URL is required for staging and production")
        if not self.api_public_url:
            raise ValueError("API_PUBLIC_URL is required for staging and production")
        if not self.cors_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS is required for staging and production")
        if "*" in self.cors_origins:
            raise ValueError("CORS wildcard origins are not allowed in staging or production")
        if self.auth_secret_key in {"", "dev-only-change-me-32-byte-minimum-key"} or len(self.auth_secret_key) < 32:
            raise ValueError("AUTH_SECRET_KEY must be changed and at least 32 characters in staging and production")
        if self.minio_root_user == "minioadmin" or self.minio_root_password == "minioadmin":
            raise ValueError("Default MinIO credentials are not allowed in staging or production")
        if self.app_env == "production":
            if self.allow_demo_reset:
                raise ValueError("ALLOW_DEMO_RESET cannot be true in production")
            if not self.auth_enabled:
                raise ValueError("AUTH_ENABLED must be true in production")
            if self.demo_mode and not self.allow_demo_mode_in_production:
                raise ValueError("DEMO_MODE cannot be true in production unless explicitly allowed")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
