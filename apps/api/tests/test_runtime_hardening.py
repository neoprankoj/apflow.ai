from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.api import dependencies
from app.core.config import Settings, settings
from app.db.session import get_database_url
from main import create_app


def test_database_url_comes_from_settings():
    original = settings.database_url
    settings.database_url = "sqlite+pysqlite:///:memory:"
    try:
        assert get_database_url() == "sqlite+pysqlite:///:memory:"
    finally:
        settings.database_url = original


def test_repository_mode_selection_uses_in_memory_default():
    dependencies.get_repository.cache_clear()
    original = settings.use_in_memory_repositories
    settings.use_in_memory_repositories = True
    try:
        repository = dependencies.get_repository()
        assert repository.__class__.__name__ == "InMemoryAPRepository"
    finally:
        settings.use_in_memory_repositories = original
        dependencies.get_repository.cache_clear()


def test_ready_endpoint_reports_in_memory_runtime_checks():
    response = TestClient(create_app()).get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["repository_mode"] == "in_memory"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["ocr"]["provider"] == "mock"
    assert body["checks"]["document_storage"]["provider"] == "memory"
    assert {"priority", "odoo", "zoho_books"}.issubset(set(body["checks"]["erp_adapters"]["available"]))


def test_ready_endpoint_reports_selected_azure_ocr_missing_credentials_as_not_ready():
    original_provider = settings.ocr_provider
    original_endpoint = settings.azure_document_intelligence_endpoint
    original_key = settings.azure_document_intelligence_key
    settings.ocr_provider = "azure"
    settings.azure_document_intelligence_endpoint = ""
    settings.azure_document_intelligence_key = ""
    try:
        response = TestClient(create_app()).get("/ready")
    finally:
        settings.ocr_provider = original_provider
        settings.azure_document_intelligence_endpoint = original_endpoint
        settings.azure_document_intelligence_key = original_key

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["ocr"]["provider"] == "azure"
    assert body["checks"]["ocr"]["status"] == "degraded"
    assert body["checks"]["ocr"]["provider_status"] == "missing_credentials"


def test_ready_endpoint_reports_selected_ocr_space_missing_credentials_as_not_ready():
    original_provider = settings.ocr_provider
    original_key = settings.ocr_space_api_key
    settings.ocr_provider = "ocr_space"
    settings.ocr_space_api_key = ""
    try:
        response = TestClient(create_app()).get("/ready")
    finally:
        settings.ocr_provider = original_provider
        settings.ocr_space_api_key = original_key

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["ocr"]["provider"] == "ocr_space"
    assert body["checks"]["ocr"]["status"] == "degraded"
    assert body["checks"]["ocr"]["provider_status"] == "missing_credentials"


def test_ready_endpoint_stays_ready_in_mock_mode_without_ocr_space_key():
    original_provider = settings.ocr_provider
    original_key = settings.ocr_space_api_key
    settings.ocr_provider = "mock"
    settings.ocr_space_api_key = ""
    try:
        response = TestClient(create_app()).get("/ready")
    finally:
        settings.ocr_provider = original_provider
        settings.ocr_space_api_key = original_key

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["ocr"]["provider"] == "mock"


def test_cors_origins_parse_and_deduplicate():
    config = Settings(
        cors_allowed_origins="http://localhost:3000, http://localhost:3000/,https://staging.example.com/"
    )

    assert config.cors_origins == ["http://localhost:3000", "https://staging.example.com"]


def test_staging_env_config_loads_with_secure_values():
    config = Settings(
        app_env="staging",
        public_app_url="https://apflow-staging.example.com",
        api_public_url="https://api.apflow-staging.example.com",
        cors_allowed_origins="https://apflow-staging.example.com",
        auth_enabled=True,
        demo_mode=True,
        auth_secret_key="staging-secret-key-change-me-32-chars",
        minio_root_user="apflow-staging-minio",
        minio_root_password="apflow-staging-minio-password",
        database_url="postgresql+psycopg://apflow:secret@postgres:5432/apflow",
    )

    assert config.app_env == "staging"
    assert config.cors_origins == ["https://apflow-staging.example.com"]


def test_production_env_fails_if_auth_secret_key_missing_or_weak():
    with pytest.raises(ValidationError, match="AUTH_SECRET_KEY"):
        Settings(
            app_env="production",
            public_app_url="https://apflow.example.com",
            api_public_url="https://api.apflow.example.com",
            cors_allowed_origins="https://apflow.example.com",
            auth_enabled=True,
            demo_mode=False,
            auth_secret_key="short",
            minio_root_user="apflow-minio",
            minio_root_password="apflow-minio-password",
            database_url="postgresql+psycopg://apflow:secret@postgres:5432/apflow",
        )


def test_production_env_fails_if_auth_disabled():
    with pytest.raises(ValidationError, match="AUTH_ENABLED"):
        Settings(
            app_env="production",
            public_app_url="https://apflow.example.com",
            api_public_url="https://api.apflow.example.com",
            cors_allowed_origins="https://apflow.example.com",
            auth_enabled=False,
            demo_mode=False,
            auth_secret_key="production-secret-key-change-me-32-chars",
            minio_root_user="apflow-minio",
            minio_root_password="apflow-minio-password",
            database_url="postgresql+psycopg://apflow:secret@postgres:5432/apflow",
        )


def test_production_env_fails_if_demo_mode_enabled():
    with pytest.raises(ValidationError, match="DEMO_MODE"):
        Settings(
            app_env="production",
            public_app_url="https://apflow.example.com",
            api_public_url="https://api.apflow.example.com",
            cors_allowed_origins="https://apflow.example.com",
            auth_enabled=True,
            demo_mode=True,
            auth_secret_key="production-secret-key-change-me-32-chars",
            minio_root_user="apflow-minio",
            minio_root_password="apflow-minio-password",
            database_url="postgresql+psycopg://apflow:secret@postgres:5432/apflow",
        )
