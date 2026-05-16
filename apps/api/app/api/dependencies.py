from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Query
from fastapi.params import Depends as DependsMarker
from sqlalchemy.orm import Session

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
from app.core.auth import AuthService
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import CurrentUserContext, MetricEventInput, Permission
from app.db.repositories import SQLAlchemyAPRepository
from app.db.session import SessionLocal, get_db_session
from app.integrations.ocr.factory import OCRProviderFactory
from app.integrations.storage.mock import FileSystemStorageAdapter, InMemoryStorageAdapter


@lru_cache
def get_in_memory_repository() -> InMemoryAPRepository:
    return InMemoryAPRepository()


def get_repository(session: Session = Depends(get_db_session)):
    if settings.use_in_memory_repositories:
        return get_in_memory_repository()
    if isinstance(session, DependsMarker):
        return SQLAlchemyAPRepository(SessionLocal())
    return SQLAlchemyAPRepository(session)


def get_audit_agent(repository=Depends(get_repository)) -> AuditLoggingAgent:
    return AuditLoggingAgent(repository=repository)


@lru_cache
def get_monitoring_agent() -> MonitoringAgent:
    return MonitoringAgent()


def get_error_handler_agent(
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
) -> ErrorHandlerAgent:
    return ErrorHandlerAgent(audit_agent=audit_agent, monitoring_agent=monitoring_agent)


def get_tenant_security_agent(
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> TenantSecurityAgent:
    return TenantSecurityAgent(audit_agent=audit_agent)


def get_orchestrator_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> APWorkflowOrchestratorAgent:
    return APWorkflowOrchestratorAgent(
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
        repository=repository,
    )


def get_invoice_ingestion_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> InvoiceIngestionAgent:
    return InvoiceIngestionAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_invoice_extraction_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> InvoiceExtractionAgent:
    return InvoiceExtractionAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_human_review_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> HumanReviewAgent:
    return HumanReviewAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@lru_cache
def get_ocr_provider_factory() -> OCRProviderFactory:
    return OCRProviderFactory()


@lru_cache
def get_storage_adapter():
    if settings.document_storage_provider == "filesystem":
        return FileSystemStorageAdapter(settings.document_storage_path)
    return InMemoryStorageAdapter()


def get_invoice_normalization_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> InvoiceNormalizationAgent:
    return InvoiceNormalizationAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_supplier_identity_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> SupplierIdentityAgent:
    return SupplierIdentityAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_invoice_validation_agent(
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> InvoiceValidationAgent:
    return InvoiceValidationAgent(
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_duplicate_detection_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> DuplicateDetectionAgent:
    return DuplicateDetectionAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_purchase_order_matching_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> PurchaseOrderMatchingAgent:
    return PurchaseOrderMatchingAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_fraud_risk_scoring_agent(
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> FraudRiskScoringAgent:
    return FraudRiskScoringAgent(
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_approval_routing_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> ApprovalRoutingAgent:
    return ApprovalRoutingAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_notification_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> NotificationAgent:
    return NotificationAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_vendor_communication_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> VendorCommunicationAgent:
    return VendorCommunicationAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_payment_status_chatbot_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
    vendor_communication_agent: VendorCommunicationAgent = Depends(get_vendor_communication_agent),
) -> PaymentStatusChatbotAgent:
    return PaymentStatusChatbotAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
        vendor_communication_agent=vendor_communication_agent,
    )


def get_erp_connector_agent(
    repository=Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    error_handler_agent: ErrorHandlerAgent = Depends(get_error_handler_agent),
) -> ERPConnectorAgent:
    return ERPConnectorAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


def get_auth_service(repository=Depends(get_repository)) -> AuthService:
    return AuthService(repository=repository)


def get_optional_current_user(
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> CurrentUserContext | None:
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
    context: CurrentUserContext | None = Depends(get_optional_current_user),
) -> CurrentUserContext:
    if context is None:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication")
    return context


def require_permission(permission: Permission):
    async def guarded(
        context: CurrentUserContext = Depends(get_current_user),
        auth_service: AuthService = Depends(get_auth_service),
        monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    ) -> CurrentUserContext:
        if not settings.auth_enabled:
            return context
        if not auth_service.user_has_permission(context, permission):
            monitoring_agent.record_metric(
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
    context: CurrentUserContext | None = Depends(get_optional_current_user),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
) -> UUID:
    if not settings.auth_enabled:
        if tenant_id is not None:
            return tenant_id
        return UUID(settings.demo_tenant_id)
    if context is None:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication")
    if tenant_id is not None and tenant_id != context.tenant.id:
        monitoring_agent.record_metric(
            MetricEventInput(
                tenant_id=context.tenant.id,
                metric_event="authorization.tenant_violation",
                value=1,
                metadata={"requested_tenant_id": str(tenant_id), "user_id": str(context.user.id)},
            )
        )
        raise HTTPException(status_code=403, detail="Tenant access denied")
    return context.tenant.id


def clear_dependency_caches() -> None:
    for provider in (
        get_in_memory_repository,
        get_monitoring_agent,
        get_ocr_provider_factory,
        get_storage_adapter,
    ):
        provider.cache_clear()


def _clear_request_scoped_dependencies() -> None:
    clear_dependency_caches()


# Several tests clear old cached providers between cases. Keep that surface while
# request-scoped dependencies intentionally no longer hold shared instances.
get_repository.cache_clear = get_in_memory_repository.cache_clear  # type: ignore[attr-defined]
for _provider in (
    get_audit_agent,
    get_error_handler_agent,
    get_tenant_security_agent,
    get_orchestrator_agent,
    get_invoice_ingestion_agent,
    get_invoice_extraction_agent,
    get_human_review_agent,
    get_invoice_normalization_agent,
    get_supplier_identity_agent,
    get_invoice_validation_agent,
    get_duplicate_detection_agent,
    get_purchase_order_matching_agent,
    get_fraud_risk_scoring_agent,
    get_approval_routing_agent,
    get_notification_agent,
    get_vendor_communication_agent,
    get_payment_status_chatbot_agent,
    get_erp_connector_agent,
    get_auth_service,
):
    _provider.cache_clear = _clear_request_scoped_dependencies  # type: ignore[attr-defined]
