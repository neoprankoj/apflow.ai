from uuid import uuid4

import pytest

from app.agents.logic.tenant_security_agent import TenantSecurityAgent
from app.agents.data.invoice_extraction_agent import InvoiceExtractionAgent
from app.agents.data.erp_connector_agent import ERPConnectorAgent
from app.agents.data.invoice_ingestion_agent import InvoiceIngestionAgent
from app.agents.data.invoice_normalization_agent import InvoiceNormalizationAgent
from app.agents.interface.human_review_agent import HumanReviewAgent
from app.agents.interface.notification_agent import NotificationAgent
from app.agents.logic.approval_routing_agent import ApprovalRoutingAgent
from app.agents.logic.duplicate_detection_agent import DuplicateDetectionAgent
from app.agents.logic.fraud_risk_scoring_agent import FraudRiskScoringAgent
from app.agents.logic.invoice_validation_agent import InvoiceValidationAgent
from app.agents.logic.purchase_order_matching_agent import PurchaseOrderMatchingAgent
from app.agents.logic.supplier_identity_agent import SupplierIdentityAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.agents.orchestration.ap_workflow_orchestrator_agent import APWorkflowOrchestratorAgent
from app.core.repositories import InMemoryAPRepository


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def audit_agent():
    return AuditLoggingAgent()


@pytest.fixture
def repository():
    return InMemoryAPRepository()


@pytest.fixture
def monitoring_agent():
    return MonitoringAgent()


@pytest.fixture
def error_handler_agent(audit_agent, monitoring_agent):
    return ErrorHandlerAgent(audit_agent=audit_agent, monitoring_agent=monitoring_agent)


@pytest.fixture
def security_agent(audit_agent, tenant_id):
    return TenantSecurityAgent(
        audit_agent=audit_agent,
        tenant_memberships={"user-1": {tenant_id}},
    )


@pytest.fixture
def orchestrator(audit_agent, monitoring_agent, error_handler_agent):
    return APWorkflowOrchestratorAgent(
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def invoice_ingestion_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return InvoiceIngestionAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def invoice_extraction_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return InvoiceExtractionAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def invoice_normalization_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return InvoiceNormalizationAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def supplier_identity_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return SupplierIdentityAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def invoice_validation_agent(audit_agent, monitoring_agent, error_handler_agent):
    return InvoiceValidationAgent(
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def duplicate_detection_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return DuplicateDetectionAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def purchase_order_matching_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return PurchaseOrderMatchingAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def fraud_risk_scoring_agent(audit_agent, monitoring_agent, error_handler_agent):
    return FraudRiskScoringAgent(
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def approval_routing_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return ApprovalRoutingAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def notification_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return NotificationAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def erp_connector_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return ERPConnectorAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )


@pytest.fixture
def human_review_agent(repository, audit_agent, monitoring_agent, error_handler_agent):
    return HumanReviewAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
    )
