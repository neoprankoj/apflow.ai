"use client";

import { Activity, Bell, FileSearch, ScanText, Send, ShieldCheck, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { cn } from "../lib/utils";

type InvoiceRecord = {
  invoice_id: string;
  canonical_invoice: {
    invoice_number: string;
    supplier_name: string;
  };
};

export type AuditEvent = {
  audit_event_id: string;
  actor_type?: string | null;
  actor_id?: string | null;
  action?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  metadata?: Record<string, unknown> | null;
  recorded_at?: string | null;
};

type WorkflowState = {
  workflow_id: string;
  state: string;
  status: string;
  current_agent: string | null;
  updated_at?: string | null;
};

type ReviewTask = {
  task_id: string;
  invoice_id?: string | null;
  status: string;
  issues: Array<{ field_name: string; issue_type: string; message: string }>;
  updated_at?: string | null;
  created_at?: string | null;
};

type NotificationEvent = {
  notification_id: string;
  invoice_id: string;
  notification_type: string;
  recipient_role: string;
  status: string;
  channel: string;
};

type TimelineUser = {
  user: {
    id: string;
    email: string;
    full_name: string;
  };
};

type Filter = "all" | "approval" | "review" | "ocr" | "erp" | "vendor" | "system";
type Source = Exclude<Filter, "all">;

type TimelineItem = {
  id: string;
  source: Source;
  title: string;
  description: string;
  invoiceId?: string | null;
  invoiceNumber?: string | null;
  vendorName?: string | null;
  actor?: string | null;
  sourceLabel: string;
  status?: string | null;
  timestamp?: string | null;
  metadata?: Record<string, unknown> | null;
};

export function AuditTimeline({
  auditEvents,
  workflows,
  notifications,
  reviewTasks,
  invoices,
  currentUser,
  tenantUsers,
  isLoading,
  canAudit
}: {
  auditEvents: AuditEvent[];
  workflows: WorkflowState[];
  notifications: NotificationEvent[];
  reviewTasks: ReviewTask[];
  invoices: InvoiceRecord[];
  currentUser: TimelineUser | null;
  tenantUsers: TimelineUser[];
  isLoading: boolean;
  canAudit: boolean;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const items = useMemo(
    () => buildTimelineItems(auditEvents, workflows, notifications, reviewTasks, invoices, currentUser, tenantUsers),
    [auditEvents, currentUser, invoices, notifications, reviewTasks, tenantUsers, workflows]
  );
  const visibleItems = filter === "all" ? items : items.filter((item) => item.source === filter);

  return (
    <section className="scroll-mt-6 space-y-4" id="audit-trail">
      <div>
        <h2 className="text-lg font-semibold">Audit Trail</h2>
        <p className="text-sm text-muted">
          A readable history of invoice, review, approval, vendor, and ERP activity.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <p className="text-sm font-medium">Activity timeline</p>
            <p className="mt-1 text-sm text-muted">
              {canAudit ? `${visibleItems.length} events visible` : "Audit permission is required to load system history."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["all", "All"],
              ["approval", "Approval"],
              ["review", "Review"],
              ["ocr", "OCR"],
              ["erp", "ERP"],
              ["vendor", "Vendor"],
              ["system", "System"]
            ].map(([value, label]) => (
              <Button
                className={cn(
                  "rounded-md",
                  filter === value
                    ? "border-primary bg-blue-50 font-medium text-primary"
                    : ""
                )}
                key={value}
                onClick={() => setFilter(value as Filter)}
                size="sm"
                variant="secondary"
              >
                {label}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[0, 1, 2, 3].map((item) => (
                <div className="flex gap-4" key={item}>
                  <LoadingSkeleton className="h-10 w-10 shrink-0 rounded-full" />
                  <div className="w-full space-y-2">
                    <LoadingSkeleton className="h-4 w-48" />
                    <LoadingSkeleton className="h-4 w-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : !canAudit ? (
            <EmptyState
              description="Your role does not have audit access. Approval and processing actions still remain available where permitted."
              title="Audit trail unavailable"
            />
          ) : visibleItems.length ? (
            <ol className="space-y-5">
              {visibleItems.slice(0, 20).map((item) => (
                <TimelineRow item={item} key={item.id} />
              ))}
            </ol>
          ) : (
            <EmptyState
              description="Workflow activity will appear here after upload, review, approval, export, or Priority import actions."
              title="No activity recorded"
            />
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function TimelineRow({ item }: { item: TimelineItem }) {
  const Icon = iconFor(item.source);
  return (
    <li className="grid gap-3 sm:grid-cols-[40px_1fr_auto]">
      <span className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-muted">
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium">{item.title}</p>
          <StatusBadge status={item.source} />
          {item.status ? <StatusBadge status={item.status} /> : null}
        </div>
        <p className="mt-1 text-sm text-muted">{item.description}</p>
        <div className="mt-3 space-y-1 text-xs text-muted">
          <p>
            <span className="font-medium text-foreground">Invoice</span>{" "}
            {item.invoiceNumber ?? "not linked"}
            {item.vendorName ? ` · ${item.vendorName}` : ""}
          </p>
          <p>
            <span className="font-medium text-foreground">Actor</span> {item.actor ?? "System"}
          </p>
          <p>
            <span className="font-medium text-foreground">Source</span> {item.sourceLabel}
          </p>
        </div>
        {item.metadata && hasMetadata(item.metadata) ? (
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer select-none">Details</summary>
            <FriendlyMetadata metadata={item.metadata} />
          </details>
        ) : null}
      </div>
      <time className="text-sm text-muted sm:text-right">{formatTimestamp(item.timestamp)}</time>
    </li>
  );
}

function buildTimelineItems(
  auditEvents: AuditEvent[],
  workflows: WorkflowState[],
  notifications: NotificationEvent[],
  reviewTasks: ReviewTask[],
  invoices: InvoiceRecord[],
  currentUser: TimelineUser | null,
  tenantUsers: TimelineUser[]
) {
  const invoiceById = new Map(invoices.map((invoice) => [invoice.invoice_id, invoice]));
  const actorNamesById = new Map(
    [currentUser, ...tenantUsers]
      .filter((user): user is TimelineUser => Boolean(user))
      .map((user) => [user.user.id, user.user.full_name || user.user.email])
  );
  const items = [
    ...auditEvents.map((event) => {
      const action = safeString(event.action);
      const metadata = safeMetadata(event.metadata);
      const source = sourceForAction(action);
      const invoice = invoiceById.get(safeString(event.entity_id));
      return {
        id: `audit-${event.audit_event_id}`,
        source,
        title: titleForAuditAction(action),
        description: descriptionForAuditAction(action, metadata),
        invoiceId: event.entity_type === "invoice" ? event.entity_id : null,
        invoiceNumber: invoice?.canonical_invoice.invoice_number ?? readMetadataText(metadata, "invoice_number"),
        vendorName: invoice?.canonical_invoice.supplier_name ?? readMetadataText(metadata, "supplier_name"),
        actor: actorLabel(event.actor_type, event.actor_id, actorNamesById),
        sourceLabel: sourceLabelForAction(action),
        status: readAuditStatus(action, metadata),
        timestamp: event.recorded_at,
        metadata
      } satisfies TimelineItem;
    }),
    ...reviewTasks.map((task) => {
      const invoice = task.invoice_id ? invoiceById.get(task.invoice_id) : null;
      return {
        id: `review-${task.task_id}`,
        source: "review",
        title: task.status === "corrected" ? "Corrections submitted" : "Human review required",
        description:
          task.issues[0]?.message ??
          (task.status === "corrected" ? "Review corrections were saved." : "Review task created."),
        invoiceId: task.invoice_id,
        invoiceNumber: invoice?.canonical_invoice.invoice_number ?? null,
        vendorName: invoice?.canonical_invoice.supplier_name ?? null,
        actor: "Human review",
        sourceLabel: "Human review",
        status: task.status,
        timestamp: task.updated_at ?? task.created_at ?? null,
        metadata: task.issues.length ? { issue_count: task.issues.length } : null
      } satisfies TimelineItem;
    }),
    ...workflows.map((workflow) => {
      const invoice = invoiceById.get(workflow.workflow_id);
      return {
        id: `workflow-${workflow.workflow_id}-${workflow.updated_at ?? workflow.status}`,
        source: "system",
        title: titleForWorkflowState(workflow.state),
        description: descriptionForWorkflowState(workflow.state, workflow.status, workflow.current_agent),
        invoiceId: workflow.workflow_id,
        invoiceNumber: invoice?.canonical_invoice.invoice_number ?? null,
        vendorName: invoice?.canonical_invoice.supplier_name ?? null,
        actor: workflowActorLabel(workflow.current_agent),
        sourceLabel: workflowSourceLabel(workflow.current_agent),
        status: workflow.status,
        timestamp: workflow.updated_at ?? null,
        metadata: null
      } satisfies TimelineItem;
    }),
    ...notifications.map((event) => {
      const invoice = invoiceById.get(event.invoice_id);
      return {
        id: `notification-${event.notification_id}`,
        source: sourceForNotification(event.notification_type),
        title: titleForNotification(event.notification_type),
        description: descriptionForNotification(event),
        invoiceId: event.invoice_id,
        invoiceNumber: invoice?.canonical_invoice.invoice_number ?? null,
        vendorName: invoice?.canonical_invoice.supplier_name ?? null,
        actor: "System",
        sourceLabel: sourceLabelForNotification(event.notification_type),
        status: event.status,
        timestamp: null,
        metadata: null
      } satisfies TimelineItem;
    })
  ];

  return items.sort((left, right) => timestampValue(right.timestamp) - timestampValue(left.timestamp));
}

function sourceForAction(action: string): Source {
  if (action.startsWith("invoice.extracted")) return "ocr";
  if (action.startsWith("review.")) return "review";
  if (action.startsWith("invoice.approval_") || action.startsWith("approval.")) return "approval";
  if (action.startsWith("erp.")) return "erp";
  if (action.startsWith("vendor.")) return "vendor";
  return "system";
}

function sourceForNotification(notificationType: string): Source {
  if (notificationType.includes("approval")) return "approval";
  if (notificationType.includes("vendor")) return "vendor";
  return "system";
}

function titleForAuditAction(action: string) {
  const labels: Record<string, string> = {
    "invoice.received": "Invoice uploaded",
    "invoice.extracted": "OCR extracted",
    "invoice.normalized": "Invoice normalized",
    "invoice.validated": "Invoice validated",
    "invoice.duplicate_scored": "Duplicate check completed",
    "supplier.matched": "Supplier matched",
    "po.matched": "PO matching completed",
    "fraud.risk_scored": "Risk scored",
    "approval.routed": "Approval routed",
    "invoice.approval_approve": "Invoice approved",
    "invoice.approval_reject": "Invoice rejected",
    "invoice.approval_hold": "Invoice placed on hold",
    "review.inspected": "Human review inspected",
    "review.corrected": "Corrections submitted",
    "vendor.access_created": "Vendor-safe preview generated",
    "vendor.message_submitted": "Vendor message received",
    "payment.status_created": "Payment status created",
    "payment.status_updated": "Payment status updated",
    "payment.mock_sync_run": "Mock payment sync run",
    "notification.sent": "Notification created"
  };
  if (action.startsWith("erp.")) return titleForErpAction(action);
  return labels[action] ?? "Activity recorded";
}

function descriptionForAuditAction(action: string, metadata: Record<string, unknown> | null) {
  if (action === "invoice.approval_approve") return "Approved by an authorized reviewer.";
  if (action === "invoice.approval_reject") return "Rejected by an authorized reviewer.";
  if (action === "invoice.approval_hold") return "Placed on hold for AP follow-up.";
  if (action === "approval.routed") return "Approval workflow evaluated this invoice.";
  if (action === "review.corrected") return "Corrected fields were submitted for review.";
  if (action === "review.inspected") return "Some extracted fields need human review.";
  if (action === "invoice.extracted") return "OCR extraction completed for the uploaded document.";
  if (action === "invoice.duplicate_scored") return "Possible duplicate invoice detection completed.";
  if (action === "po.matched") return "PO matching was evaluated for this invoice.";
  if (action === "fraud.risk_scored") return "Risk screening was completed.";
  if (action.startsWith("erp.export_invoice")) return "Invoice exported to mock Priority ERP.";
  if (action === "payment.status_created") return "Payment tracking was created for this invoice.";
  if (action === "payment.status_updated") {
    const status = readMetadataText(metadata, "status");
    return status ? `Payment status updated to ${humanize(status)}.` : "Payment status was updated.";
  }
  if (action === "payment.mock_sync_run") return "Mock payment sync updated APFlow payment statuses only.";
  if (action.startsWith("erp.")) return "ERP activity was recorded.";
  if (action === "notification.sent") {
    const type = readMetadataText(metadata, "notification_type");
    return type ? `${humanize(type)} notification recorded.` : "A notification event was recorded.";
  }
  return "System activity was recorded.";
}

function titleForErpAction(action: string) {
  if (action.includes("export_invoice")) return "Exported to ERP";
  if (action.includes("sync_payment_status")) return "Payment status synced";
  if (action.includes("sync_purchase_orders")) return "Purchase orders synced";
  if (action.includes("sync_vendors")) return "Vendors synced";
  return "ERP activity recorded";
}

function titleForWorkflowState(state: string) {
  const labels: Record<string, string> = {
    blocked: "Invoice blocked",
    approval_ready: "Invoice ready for approval",
    auto_approved: "Invoice auto-approved",
    rejected: "Invoice rejected",
    review_required: "Human review required"
  };
  return labels[state] ?? "Workflow updated";
}

function descriptionForWorkflowState(state: string, status: string, currentAgent: string | null) {
  if (state === "blocked") return "Invoice requires AP review before export.";
  if (state === "review_required") return "Some extracted fields need human review.";
  if (state === "approval_ready") return "Invoice is ready for approval or export.";
  if (state === "rejected") return "Invoice was rejected by an authorized reviewer.";
  if (state === "auto_approved") return "Invoice passed the configured approval workflow.";
  if (currentAgent) return `${humanize(status)} by ${workflowActorLabel(currentAgent)}.`;
  return `Workflow status is ${humanize(status)}.`;
}

function titleForNotification(notificationType: string) {
  const labels: Record<string, string> = {
    approval_required: "Approval requested",
    approval_decision_recorded: "Approval decision recorded",
    duplicate_detected: "Duplicate detected",
    invoice_blocked: "Invoice blocked",
    validation_failed: "Validation failed"
  };
  return labels[notificationType] ?? "Notification created";
}

function descriptionForNotification(event: NotificationEvent) {
  if (event.notification_type === "invoice_blocked") return "Invoice requires AP review before export.";
  if (event.notification_type === "duplicate_detected") return "Possible duplicate invoice detected.";
  if (event.notification_type === "approval_required") return "Approval is required before the invoice can continue.";
  if (event.notification_type === "approval_decision_recorded") return "Approval decision recorded for the invoice.";
  return `${titleCase(humanize(event.status))} via ${event.channel} for ${humanize(event.recipient_role)}.`;
}

function readAuditStatus(action: string, metadata: Record<string, unknown> | null) {
  if (action.startsWith("invoice.approval_")) return readMetadataText(metadata, "approval_status");
  if (action === "fraud.risk_scored") return readMetadataText(metadata, "risk_level");
  if (action === "po.matched") return readMetadataText(metadata, "match_status");
  return null;
}

function actorLabel(
  actorType: string | null | undefined,
  actorId: string | null | undefined,
  actorNamesById: Map<string, string>
) {
  const normalizedActor = safeString(actorId);
  if (normalizedActor && actorNamesById.has(normalizedActor)) return actorNamesById.get(normalizedActor) ?? "Authorized reviewer";
  if (actorType === "user") {
    if (normalizedActor.includes("@")) return normalizedActor;
    return "Authorized reviewer";
  }
  if (normalizedActor) return agentLabel(normalizedActor);
  return "System";
}

function workflowActorLabel(agent: string | null) {
  return agent ? agentLabel(agent) : "System";
}

function workflowSourceLabel(agent: string | null) {
  if (!agent) return "Workflow engine";
  return agentLabel(agent);
}

function sourceLabelForAction(action: string) {
  if (action.startsWith("invoice.approval_") || action.startsWith("approval.")) return "Approval workflow";
  if (action.startsWith("review.")) return "Human review";
  if (action.startsWith("invoice.extracted")) return "OCR service";
  if (action.startsWith("erp.")) return "ERP connector";
  if (action.startsWith("vendor.")) return "Vendor portal";
  return "System";
}

function sourceLabelForNotification(notificationType: string) {
  if (notificationType.includes("approval")) return "Approval workflow";
  if (notificationType.includes("vendor")) return "Vendor portal";
  return "System";
}

function agentLabel(value: string) {
  const labels: Record<string, string> = {
    ApprovalRoutingAgent: "Approval workflow",
    HumanReviewAgent: "Human review",
    InvoiceExtractionAgent: "OCR service",
    OCRExtractionAgent: "OCR service",
    APWorkflowOrchestratorAgent: "Workflow engine"
  };
  return labels[value] ?? "System";
}

function iconFor(source: Source) {
  if (source === "approval") return UserRound;
  if (source === "review") return FileSearch;
  if (source === "ocr") return ScanText;
  if (source === "erp") return Send;
  if (source === "vendor") return Bell;
  if (source === "system") return ShieldCheck;
  return Activity;
}

function safeString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function safeMetadata(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function readMetadataText(metadata: Record<string, unknown> | null, key: string) {
  const value = metadata?.[key];
  return typeof value === "string" ? value : null;
}

function hasMetadata(metadata: Record<string, unknown> | null | undefined) {
  return Boolean(metadata && Object.keys(metadata).length);
}

function FriendlyMetadata({ metadata }: { metadata: Record<string, unknown> }) {
  const rows = friendlyMetadataRows(metadata);
  return (
    <div className="mt-2 space-y-3 rounded-md bg-slate-50 p-3">
      {rows.length ? (
        <dl className="grid gap-2 sm:grid-cols-[140px_1fr]">
          {rows.map((row) => (
            <div className="contents" key={row.label}>
              <dt className="font-medium text-foreground">{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>No friendly details available.</p>
      )}
      <details>
        <summary className="cursor-pointer select-none">Raw metadata</summary>
        <pre className="mt-2 overflow-x-auto rounded-md bg-white p-3">
          {JSON.stringify(metadata, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function friendlyMetadataRows(metadata: Record<string, unknown>) {
  return [
    ["approval_status", "Approval status"],
    ["route", "Approval route"],
    ["reason", "Reason"],
    ["approval_task_id", "Approval task"],
    ["invoice_id", "Invoice ID"],
    ["external_id", "External ERP ID"],
    ["provider", "Provider"]
  ]
    .map(([key, label]) => {
      const value = metadata[key];
      if (value === undefined || value === null || value === "") return null;
      return { label, value: metadataValueLabel(key, value) };
    })
    .filter((row): row is { label: string; value: string } => Boolean(row));
}

function metadataValueLabel(key: string, value: unknown) {
  if (typeof value !== "string") return String(value);
  if (key === "approval_status") return titleCase(humanize(value));
  if (key === "route") return approvalRouteLabel(value);
  return value;
}

function approvalRouteLabel(value: string) {
  const labels: Record<string, string> = {
    blocked: "Blocked invoice review",
    ap_review: "AP review",
    manager_approval: "Manager approval",
    controller_approval: "Controller approval",
    auto_approve: "Auto approve"
  };
  return labels[value] ?? titleCase(humanize(value));
}

function titleCase(value: string) {
  return value.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function timestampValue(value?: string | null) {
  const parsed = value ? new Date(value) : null;
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : 0;
}

function formatTimestamp(value?: string | null) {
  const parsed = value ? new Date(value) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(parsed);
}

function humanize(value: string) {
  return value.replaceAll("_", " ");
}
