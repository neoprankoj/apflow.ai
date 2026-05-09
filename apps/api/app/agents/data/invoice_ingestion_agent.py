from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    InvoiceIngestionInput,
    InvoiceIngestionOutput,
    MetricEventInput,
    WorkflowErrorInput,
)
from app.integrations.storage.mock import MockObjectStorage


SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/xml",
    "text/xml",
}


class InvoiceIngestionAgent(BaseAgent[InvoiceIngestionInput, InvoiceIngestionOutput]):
    name = "InvoiceIngestionAgent"
    responsibility = "Receive invoices from supported channels and create raw invoice records."

    def __init__(
        self,
        repository: InMemoryAPRepository,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        storage: MockObjectStorage | None = None,
    ) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.storage = storage or MockObjectStorage()

    def ingest(self, request: InvoiceIngestionInput) -> InvoiceIngestionOutput:
        try:
            if request.metadata.mime_type not in SUPPORTED_MIME_TYPES:
                raise ValueError(f"unsupported invoice MIME type: {request.metadata.mime_type}")

            storage_url, checksum = self.storage.store(
                tenant_id=str(request.tenant_id),
                file_url=request.file_url,
                content=request.content,
            )
            output = InvoiceIngestionOutput(
                tenant_id=request.tenant_id,
                storage_url=storage_url,
                mime_type=request.metadata.mime_type,
                source=request.source,
                file_checksum=checksum,
            )
            self.repository.store_raw_invoice(output=output, content=request.content)
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="invoice.received",
                    entity_type="raw_invoice",
                    entity_id=output.raw_invoice_id,
                    metadata={
                        "source": request.source,
                        "mime_type": output.mime_type,
                        "checksum": checksum,
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="invoice.ingested",
                    value=1,
                    metadata={"source": request.source, "mime_type": output.mime_type},
                )
            )
            return output
        except Exception as exc:
            self.error_handler_agent.handle_error(
                WorkflowErrorInput(
                    tenant_id=request.tenant_id,
                    workflow_id=request.correlation_id,
                    agent_name=self.name,
                    error_type=ErrorCategory.VALIDATION,
                    error_message=str(exc),
                    retry_count=0,
                    context={"source": request.source},
                )
            )
            raise
