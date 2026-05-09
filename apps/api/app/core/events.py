from enum import StrEnum


class WorkflowEventType(StrEnum):
    INVOICE_RECEIVED = "invoice.received"
    INVOICE_EXTRACTED = "invoice.extracted"
    INVOICE_NORMALIZED = "invoice.normalized"
    SUPPLIER_MATCHED = "supplier.matched"
    INVOICE_VALIDATED = "invoice.validated"
    INVOICE_EXCEPTION = "invoice.exception"
    APPROVAL_UPDATED = "approval.updated"
    ERP_SYNCED = "erp.synced"


NEXT_AGENT_BY_EVENT: dict[WorkflowEventType, str] = {
    WorkflowEventType.INVOICE_RECEIVED: "InvoiceExtractionAgent",
    WorkflowEventType.INVOICE_EXTRACTED: "InvoiceNormalizationAgent",
    WorkflowEventType.INVOICE_NORMALIZED: "SupplierIdentityAgent",
    WorkflowEventType.SUPPLIER_MATCHED: "InvoiceValidationAgent",
    WorkflowEventType.INVOICE_VALIDATED: "DuplicateDetectionAgent",
    WorkflowEventType.INVOICE_EXCEPTION: "ErrorHandlerAgent",
    WorkflowEventType.APPROVAL_UPDATED: "ERPConnectorAgent",
    WorkflowEventType.ERP_SYNCED: "ReportingAnalyticsAgent",
}


FOUNDATION_AGENT_ORDER = [
    "TenantSecurityAgent",
    "AuditLoggingAgent",
    "MonitoringAgent",
    "ErrorHandlerAgent",
    "APWorkflowOrchestratorAgent",
]
