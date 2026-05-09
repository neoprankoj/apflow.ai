from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, Query

from app.core.auth import AuthService
from app.agents.data.erp_connector_agent import ERPConnectorAgent
from app.agents.data.invoice_extraction_agent import InvoiceExtractionAgent
from app.agents.data.invoice_ingestion_agent import InvoiceIngestionAgent
from app.agents.data.invoice_normalization_agent import InvoiceNormalizationAgent
from app.agents.interface.human_review_agent import HumanReviewAgent
from app.agents.interface.notification_agent import NotificationAgent
from app.agents.interface.payment_status_chatbot_agent import PaymentStatusChatbotAgent
from app.agents.interface.vendor_communication_agent import VendorCommunicationAgent
from app.agents.logic.approval_routing_agent import ApprovalRoutingAgent
from app.agents.logic.duplicate_detection_agent import DuplicateDetectionAgent
from app.agents.logic.fraud_risk_scoring_agent import FraudRiskScoringAgent
from app.agents.logic.invoice_validation_agent import InvoiceValidationAgent
from app.agents.logic.purchase_order_matching_agent import PurchaseOrderMatchingAgent
from app.agents.logic.supplier_identity_agent import SupplierIdentityAgent
from app.agents.logic.tenant_security_agent import TenantSecurityAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.agents.orchestration.ap_workflow_orchestrator_agent import APWorkflowOrchestratorAgent
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import CurrentUserContext, MetricEventInput, Permission
from app.db.repositories import SQLAlchemyAPRepository
from app.db.session import SessionLocal
from app.integrations.ocr.factory import OCRProviderFactory
from app.integrations.storage.mock import FileSystemStorageAdapter, InMemoryStorageAdapter


@lru_cache
def get_repository():
    if settings.use_in_memory_repositories:
        return InMemoryAPRepository()
    return SQLAlchemyAPRepository(SessionLocal())


@lru_cache
def get_in_memory_repository() -> InMemoryAPRepository:
    return InMemoryAPRepository()


@lru_cache
def get_audit_agent() -> AuditLoggingAgent:
    return AuditLoggingAgent(repository=get_repository())


@lru_cache
def get_monitoring_agent() -> MonitoringAgent:
    return MonitoringAgent()


@lru_cache
def get_error_handler_agent() -> ErrorHandlerAgent:
    return ErrorHandlerAgent(audit_agent=get_audit_agent(), monitoring_agent=get_monitoring_agent())


@lru_cache
def get_tenant_security_agent() -> TenantSecurityAgent:
    return TenantSecurityAgent(audit_agent=get_audit_agent())


@lru_cache
def get_orchestrator_agent() -> APWorkflowOrchestratorAgent:
    return APWorkflowOrchestratorAgent(
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
        repository=get_repository(),
    )


@lru_cache
def get_invoice_ingestion_agent() -> InvoiceIngestionAgent:
    return InvoiceIngestionAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_invoice_extraction_agent() -> InvoiceExtractionAgent:
    return InvoiceExtractionAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_human_review_agent() -> HumanReviewAgent:
    return HumanReviewAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_ocr_provider_factory() -> OCRProviderFactory:
    return OCRProviderFactory()


@lru_cache
def get_storage_adapter():
    if settings.document_storage_provider == "filesystem":
        return FileSystemStorageAdapter(settings.document_storage_path)
    return InMemoryStorageAdapter()


@lru_cache
def get_invoice_normalization_agent() -> InvoiceNormalizationAgent:
    return InvoiceNormalizationAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_supplier_identity_agent() -> SupplierIdentityAgent:
    return SupplierIdentityAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_invoice_validation_agent() -> InvoiceValidationAgent:
    return InvoiceValidationAgent(
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_duplicate_detection_agent() -> DuplicateDetectionAgent:
    return DuplicateDetectionAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_purchase_order_matching_agent() -> PurchaseOrderMatchingAgent:
    return PurchaseOrderMatchingAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_fraud_risk_scoring_agent() -> FraudRiskScoringAgent:
    return FraudRiskScoringAgent(
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_approval_routing_agent() -> ApprovalRoutingAgent:
    return ApprovalRoutingAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_notification_agent() -> NotificationAgent:
    return NotificationAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_vendor_communication_agent() -> VendorCommunicationAgent:
    return VendorCommunicationAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_payment_status_chatbot_agent() -> PaymentStatusChatbotAgent:
    return PaymentStatusChatbotAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
        vendor_communication_agent=get_vendor_communication_agent(),
    )


@lru_cache
def get_erp_connector_agent() -> ERPConnectorAgent:
    return ERPConnectorAgent(
        repository=get_repository(),
        audit_agent=get_audit_agent(),
        monitoring_agent=get_monitoring_agent(),
        error_handler_agent=get_error_handler_agent(),
    )


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService(repository=get_repository())


def get_optional_current_user(
    authorization: str | None = Header(default=None),
) -> CurrentUserContext | None:
    auth_service = get_auth_service()
    if not settings.auth_enabled:
        return auth_service.demo_context() if settings.demo_mode else None
    if authorization is None or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = auth_service.decode_token(token)
        user_id = UUID(payload["sub"])
        tenant_id = UUID(payload["tenant_id"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    return auth_service.build_context(user_id=user_id, tenant_id=tenant_id)


def get_current_user(
    authorization: str | None = Header(default=None),
) -> CurrentUserContext:
    context = get_optional_current_user(authorization=authorization)
    if context is None:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication")
    return context


def require_permission(permission: Permission):
    async def guarded(
        authorization: str | None = Header(default=None),
    ) -> CurrentUserContext:
        context = get_current_user(authorization=authorization)
        if not settings.auth_enabled:
            return context
        if not get_auth_service().user_has_permission(context, permission):
            get_monitoring_agent().record_metric(
                MetricEventInput(
                    tenant_id=context.tenant.id,
                    metric_event="authorization.denied",
                    value=1,
                    metadata={
                        "permission": str(permission),
                        "user_id": str(context.user.id),
                        "role": str(context.membership.role),
                    },
                )
            )
            raise HTTPException(status_code=403, detail="Permission denied")
        return context

    return guarded


def resolve_tenant_id(
    tenant_id: UUID | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> UUID:
    if not settings.auth_enabled:
        if tenant_id is not None:
            return tenant_id
        return UUID(settings.demo_tenant_id)
    context = get_current_user(authorization=authorization)
    if tenant_id is not None and tenant_id != context.tenant.id:
        get_monitoring_agent().record_metric(
            MetricEventInput(
                tenant_id=context.tenant.id,
                metric_event="authorization.tenant_violation",
                value=1,
                metadata={"requested_tenant_id": str(tenant_id), "user_id": str(context.user.id)},
            )
        )
        raise HTTPException(status_code=403, detail="Tenant access denied")
    return context.tenant.id
