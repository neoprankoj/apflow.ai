"use client";

import { CalendarDays, ExternalLink, Send } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { cn } from "../lib/utils";
import { apiFetch } from "./frontend-api";

type InvoiceRecord = {
  invoice_id: string;
  canonical_invoice: {
    invoice_number: string;
    supplier_name: string;
    grand_total: number;
    currency: string;
    po_number?: string | null;
    due_date?: string | null;
  };
};

type ApprovalTask = {
  approval_task_id: string;
  invoice_id: string;
  route: string;
  assigned_role: string;
  status: string;
  reason: string;
};

type NotificationEvent = {
  notification_id: string;
  invoice_id: string;
  notification_type: string;
  recipient_role: string;
  status: string;
  channel: string;
  payload?: Record<string, unknown>;
};

type VendorInvoiceStatus = {
  invoice_id: string;
  invoice_number: string;
  status: string;
  payment_status: string | null;
  public_message: string;
  missing_information: string[];
  grand_total: number;
  currency: string;
};

type ApprovalDecisionResult = {
  approval_status: string;
  workflow_status: string;
  erp_export_ready: boolean;
  blocker_reason?: string | null;
};

type ERPSyncResult = {
  sync_id: string;
  adapter_type: string;
  operation: string;
  status: string;
  external_id: string | null;
};

type Filter =
  | "all"
  | "needs_action"
  | "blocked"
  | "on_hold"
  | "rejected"
  | "approval_ready"
  | "high_risk"
  | "missing_po";

type Props = {
  accessToken: string | null;
  apiBaseUrl: string | null;
  tenantId: string | null;
  invoices: InvoiceRecord[];
  approvals: ApprovalTask[];
  notifications: NotificationEvent[];
  canApproveInvoice: boolean;
  canExportErp: boolean;
  isLoading?: boolean;
  onRefresh: () => Promise<void> | void;
};

export function ApprovalInbox({
  accessToken,
  apiBaseUrl,
  tenantId,
  invoices,
  approvals,
  notifications,
  canApproveInvoice,
  canExportErp,
  isLoading = false,
  onRefresh
}: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [vendorPreview, setVendorPreview] = useState<VendorInvoiceStatus | null>(null);
  const [approvalMessage, setApprovalMessage] = useState<string | null>(null);
  const [erpMessage, setErpMessage] = useState<string | null>(null);
  const [vendorMessage, setVendorMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [erpResult, setErpResult] = useState<ERPSyncResult | null>(null);

  const inboxItems = useMemo(
    () => buildInboxItems(invoices, approvals, notifications),
    [approvals, invoices, notifications]
  );
  const filteredItems = useMemo(() => inboxItems.filter((item) => matchesFilter(item, filter)), [filter, inboxItems]);
  const selectedItem =
    inboxItems.find((item) => item.invoice.invoice_id === selectedInvoiceId) ?? filteredItems[0] ?? inboxItems[0] ?? null;
  const selectedNotifications = selectedItem
    ? notifications.filter((event) => event.invoice_id === selectedItem.invoice.invoice_id).slice(-4).reverse()
    : [];

  useEffect(() => {
    if (!selectedItem) {
      setSelectedInvoiceId(null);
      return;
    }
    if (selectedInvoiceId !== selectedItem.invoice.invoice_id) {
      setSelectedInvoiceId(selectedItem.invoice.invoice_id);
    }
  }, [selectedInvoiceId, selectedItem]);

  useEffect(() => {
    setVendorPreview(null);
    setErpResult(null);
    setApprovalMessage(null);
    setErpMessage(null);
    setVendorMessage(null);
    setError(null);
    if (!selectedItem || !apiBaseUrl || !tenantId || !accessToken) return;
    void loadVendorPreview(selectedItem.invoice.invoice_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedItem?.invoice.invoice_id, apiBaseUrl, tenantId, accessToken]);

  async function decideApproval(action: "approve" | "reject" | "hold") {
    if (!selectedItem || !apiBaseUrl || !tenantId || !accessToken || !canApproveInvoice) return;
    if (action === "reject" && !window.confirm("Reject this invoice? This keeps it out of ERP export.")) return;
    setActiveAction(action);
    setError(null);
    setApprovalMessage(null);
    try {
      const result = await apiFetch<ApprovalDecisionResult>(
        apiBaseUrl,
        `/invoices/${selectedItem.invoice.invoice_id}/approval-decision`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ tenant_id: tenantId, action }),
          token: accessToken,
          action: `${action} inbox invoice`
        }
      );
      await onRefresh();
      await loadVendorPreview(selectedItem.invoice.invoice_id);
      setApprovalMessage(
        `Approval decision saved: ${humanize(result.approval_status)}. ${
          result.blocker_reason ?? "Open Audit Trail to verify this decision."
        }`.trim()
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Approval decision failed.");
    } finally {
      setActiveAction(null);
    }
  }

  async function exportToMockErp() {
    if (!selectedItem || !apiBaseUrl || !tenantId || !accessToken || !canExportErp) return;
    setActiveAction("export");
    setError(null);
    setErpMessage(null);
    try {
      const result = await apiFetch<ERPSyncResult>(apiBaseUrl, "/erp/export-invoice", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          adapter_type: "priority",
          invoice_id: selectedItem.invoice.invoice_id
        }),
        token: accessToken,
        action: "Export inbox invoice"
      });
      setErpResult(result);
      await onRefresh();
      await loadVendorPreview(selectedItem.invoice.invoice_id);
      setErpMessage(
        `Invoice exported to mock ERP with status ${result.status}; external ID ${
          result.external_id ?? "not returned"
        }. Open Audit Trail to verify the export.`
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "ERP export failed.");
    } finally {
      setActiveAction(null);
    }
  }

  async function loadVendorPreview(invoiceId: string) {
    if (!apiBaseUrl || !tenantId || !accessToken) return;
    setVendorMessage(null);
    try {
      const preview = await apiFetch<VendorInvoiceStatus>(
        apiBaseUrl,
        `/vendor/preview/invoices/${invoiceId}?tenant_id=${tenantId}`,
        { token: accessToken, action: "Load inbox vendor preview" }
      );
      setVendorPreview(preview);
      setVendorMessage(`Vendor-safe status refreshed: ${humanize(preview.status)}. Internal risk details remain hidden.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Vendor preview failed.");
    }
  }

  return (
    <section className="scroll-mt-6 space-y-4" id="approval-inbox">
      <div>
        <h2 className="text-lg font-semibold">Approval Inbox</h2>
        <p className="text-sm text-muted">
          Use this queue to decide blocked or pending invoices, then export approval-ready invoices.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <p className="text-sm font-medium">Invoice review queue</p>
            <p className="mt-1 text-sm text-muted">{filteredItems.length} invoices visible</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["all", "All"],
              ["needs_action", "Needs action"],
              ["blocked", "Blocked"],
              ["on_hold", "On hold"],
              ["rejected", "Rejected"],
              ["approval_ready", "Approval ready"],
              ["high_risk", "High risk"],
              ["missing_po", "Missing PO"]
            ].map(([value, label]) => (
              <Button
                className={filter === value ? "border-primary bg-blue-50 text-primary" : ""}
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

        <div className="grid gap-0 lg:grid-cols-[minmax(320px,380px)_minmax(0,1fr)] xl:grid-cols-[minmax(360px,420px)_minmax(560px,1fr)]">
          <div className="border-b border-border bg-slate-50/60 lg:border-b-0 lg:border-r">
            {isLoading ? (
              <div className="space-y-3 p-4">
                {[0, 1, 2, 3].map((item) => (
                  <div className="rounded-lg border border-border bg-surface p-4" key={item}>
                    <LoadingSkeleton className="h-4 w-32" />
                    <LoadingSkeleton className="mt-3 h-4 w-44" />
                    <LoadingSkeleton className="mt-4 h-6 w-24" />
                  </div>
                ))}
              </div>
            ) : filteredItems.length ? (
              <div className="space-y-3 p-4">
                {filteredItems.map((item) => (
                  <QueueRow
                    isSelected={selectedItem?.invoice.invoice_id === item.invoice.invoice_id}
                    item={item}
                    key={item.invoice.invoice_id}
                    onClick={() => setSelectedInvoiceId(item.invoice.invoice_id)}
                  />
                ))}
              </div>
            ) : (
              <div className="p-4">
                <EmptyState
                  description="No invoices need this view right now. Try another filter or process a new invoice."
                  title="No invoices match this filter"
                />
              </div>
            )}
          </div>

          <div className="min-w-0 bg-white">
            {error ? (
              <div className="mx-5 mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                {error}
              </div>
            ) : null}

            {selectedItem ? (
              <div className="space-y-5 p-5">
                <SelectedInvoiceHeader
                  erpResult={erpResult}
                  selectedItem={selectedItem}
                  vendorPreview={vendorPreview}
                />

                <div className="grid gap-4 2xl:grid-cols-2">
                  <SectionCard title="Invoice Summary">
                    <div className="space-y-3">
                      <DetailRow label="Invoice number" value={selectedItem.invoice.canonical_invoice.invoice_number} />
                      <DetailRow label="Vendor" value={selectedItem.invoice.canonical_invoice.supplier_name} />
                      <DetailRow
                        label="Amount"
                        value={money(
                          selectedItem.invoice.canonical_invoice.grand_total,
                          selectedItem.invoice.canonical_invoice.currency
                        )}
                      />
                      <DetailRow label="Due date" value={dueDateLabel(selectedItem.dueDate)} />
                      <DetailRow label="PO match" value={<StatusBadge status={selectedItem.poMatchStatus} />} />
                      <DetailRow label="Duplicate status" value={<StatusBadge status={selectedItem.duplicateLikely ? "duplicate" : "clear"} />} />
                    </div>
                  </SectionCard>

                  <SectionCard title="Review Notes / Audit Context">
                    <div className="space-y-4">
                      <div>
                        <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted">Current blocker</p>
                        <p className="mt-1 text-sm">{selectedItem.blockerReason}</p>
                      </div>
                      <div>
                        <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted">Latest activity</p>
                        {selectedNotifications.length ? (
                          <div className="mt-2 space-y-2">
                            {selectedNotifications.map((event) => (
                              <div className="rounded-md bg-slate-50 px-3 py-2 text-sm" key={event.notification_id}>
                                <p className="font-medium">{humanize(event.notification_type)}</p>
                                <p className="mt-1 text-xs text-muted">
                                  {event.recipient_role} - {event.status} via {event.channel}
                                </p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-2 text-sm text-muted">No notification activity recorded for this invoice yet.</p>
                        )}
                      </div>
                    </div>
                  </SectionCard>
                </div>

                <div className="grid gap-4 2xl:grid-cols-3">
                  <SectionCard title="Approval Decision">
                    <div className="space-y-4">
                      <div className="flex flex-wrap gap-2">
                        <StatusBadge status={selectedItem.workflowStatus} />
                        <StatusBadge status={selectedItem.approvalStatus} />
                        {selectedItem.riskLevel !== "not recorded" ? <StatusBadge status={selectedItem.riskLevel} /> : null}
                      </div>
                      {canApproveInvoice && selectedItem.canDecide ? (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            disabled={Boolean(activeAction)}
                            onClick={() => void decideApproval("approve")}
                            variant="primary"
                          >
                            Approve
                          </Button>
                          <Button
                            disabled={Boolean(activeAction)}
                            onClick={() => void decideApproval("hold")}
                            variant="secondary"
                          >
                            Keep on Hold
                          </Button>
                          <Button
                            disabled={Boolean(activeAction)}
                            onClick={() => void decideApproval("reject")}
                            variant="danger"
                          >
                            Reject
                          </Button>
                        </div>
                      ) : (
                        <p className="text-sm text-muted">
                          No approval decision is available for this state. Approval-ready invoices can move to ERP export.
                        </p>
                      )}
                      {approvalMessage ? <FeedbackMessage>{approvalMessage}</FeedbackMessage> : null}
                    </div>
                  </SectionCard>

                  <SectionCard title="ERP Actions">
                    <div className="space-y-4">
                      <DetailRow label="Export readiness" value={<StatusBadge status={selectedItem.erpReady ? "erp_ready" : "erp_blocked"} />} />
                      <Button
                        disabled={!selectedItem.erpReady || !canExportErp || Boolean(activeAction)}
                        onClick={() => void exportToMockErp()}
                        variant="secondary"
                      >
                        <Send className="h-4 w-4" />
                        {activeAction === "export" ? "Exporting..." : "Export to Mock ERP"}
                      </Button>
                      {selectedItem.erpReady ? null : (
                        <p className="text-sm text-muted">Approval must be ready before ERP export is enabled.</p>
                      )}
                      {erpMessage ? <FeedbackMessage>{erpMessage}</FeedbackMessage> : null}
                      {erpResult ? (
                        <div className="rounded-md bg-slate-50 px-3 py-2 text-sm">
                          <p className="font-medium">Mock ERP export {erpResult.status}</p>
                          <p className="mt-1 text-xs text-muted">
                            {erpResult.adapter_type} - {erpResult.external_id ?? "no external id"}
                          </p>
                        </div>
                      ) : null}
                    </div>
                  </SectionCard>

                  <SectionCard title="Vendor Actions">
                    <div className="space-y-4">
                      <DetailRow label="Vendor-safe status" value={<StatusBadge status={vendorPreview?.status ?? "loading"} />} />
                      <div className="rounded-md bg-slate-50 px-3 py-3 text-sm">
                        {vendorPreview ? (
                          <>
                            <p className="font-medium">{humanize(vendorPreview.status)}</p>
                            <p className="mt-1 text-muted">{vendorPreview.public_message}</p>
                          </>
                        ) : (
                          <p className="text-muted">Loading vendor-safe status...</p>
                        )}
                      </div>
                      <Button
                        disabled={Boolean(activeAction)}
                        onClick={() => void loadVendorPreview(selectedItem.invoice.invoice_id)}
                        variant="secondary"
                      >
                        <ExternalLink className="h-4 w-4" />
                        Preview vendor-safe status
                      </Button>
                      {vendorMessage ? <FeedbackMessage>{vendorMessage}</FeedbackMessage> : null}
                    </div>
                  </SectionCard>
                </div>
              </div>
            ) : (
              <div className="p-5">
                <EmptyState
                  description="Choose an invoice from the queue to inspect details and take action."
                  title="No invoice selected"
                />
              </div>
            )}
          </div>
        </div>
      </Card>
    </section>
  );
}

type InboxItem = ReturnType<typeof buildInboxItems>[number];

function QueueRow({
  item,
  isSelected,
  onClick
}: {
  item: InboxItem;
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        "w-full rounded-lg border bg-surface p-4 text-left transition-all",
        "hover:border-primary/40 hover:shadow-sm focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15",
        isSelected ? "border-primary bg-blue-50/60 shadow-sm" : "border-border",
        item.isOverdue && "border-l-4 border-l-danger"
      )}
      onClick={onClick}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{item.invoice.canonical_invoice.supplier_name}</p>
          <p className="mt-1 text-sm text-muted">
            {item.invoice.canonical_invoice.invoice_number} - #{shortId(item.invoice.invoice_id)}
          </p>
        </div>
        <p className="shrink-0 text-right font-semibold">
          {money(item.invoice.canonical_invoice.grand_total, item.invoice.canonical_invoice.currency)}
        </p>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted">
          <CalendarDays className="h-4 w-4" />
          <span className={dueTone(item.dueDate)}>{dueDateLabel(item.dueDate)}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge status={item.workflowStatus} />
          {item.riskLevel !== "not recorded" ? <StatusBadge status={item.riskLevel} /> : null}
        </div>
      </div>
      {item.duplicateLikely || item.poMatchStatus === "missing_po" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {item.duplicateLikely ? <StatusBadge status="likely duplicate" /> : null}
          {item.poMatchStatus === "missing_po" ? <StatusBadge status="missing PO" /> : null}
        </div>
      ) : null}
    </button>
  );
}

function SelectedInvoiceHeader({
  selectedItem,
  vendorPreview,
  erpResult
}: {
  selectedItem: InboxItem;
  vendorPreview: VendorInvoiceStatus | null;
  erpResult: ERPSyncResult | null;
}) {
  return (
    <div className="flex flex-col gap-4 border-b border-border pb-5 xl:flex-row xl:items-start xl:justify-between">
      <div>
        <p className="text-sm font-medium text-muted">Selected invoice</p>
        <h3 className="mt-1 text-2xl font-semibold">{selectedItem.invoice.canonical_invoice.supplier_name}</h3>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <span>
            <span className="text-muted">Invoice</span>{" "}
            <strong>{selectedItem.invoice.canonical_invoice.invoice_number}</strong>
          </span>
          <span>
            <span className="text-muted">Due</span>{" "}
            <strong className={dueTone(selectedItem.dueDate)}>{dueDateLabel(selectedItem.dueDate)}</strong>
          </span>
          <span>
            <span className="text-muted">Amount</span>{" "}
            <strong>
              {money(
                selectedItem.invoice.canonical_invoice.grand_total,
                selectedItem.invoice.canonical_invoice.currency
              )}
            </strong>
          </span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 xl:max-w-xs xl:justify-end">
        <StatusBadge status={selectedItem.workflowStatus} />
        <StatusBadge status={selectedItem.approvalStatus} />
        {selectedItem.riskLevel !== "not recorded" ? <StatusBadge status={selectedItem.riskLevel} /> : null}
        {selectedItem.duplicateLikely ? <StatusBadge status="duplicate" /> : null}
        {erpResult ? <StatusBadge status="exported" /> : null}
        {vendorPreview ? <StatusBadge status={vendorPreview.status} /> : null}
      </div>
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="shadow-none">
      <CardHeader className="px-4 py-3">
        <h4 className="text-sm font-semibold">{title}</h4>
      </CardHeader>
      <CardContent className="p-4">{children}</CardContent>
    </Card>
  );
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 text-sm">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

function FeedbackMessage({ children }: { children: ReactNode }) {
  return <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-success">{children}</p>;
}

function buildInboxItems(invoices: InvoiceRecord[], approvals: ApprovalTask[], notifications: NotificationEvent[]) {
  const latestTaskByInvoice = new Map<string, ApprovalTask>();
  approvals.forEach((task) => latestTaskByInvoice.set(task.invoice_id, task));
  const duplicateInvoiceNumbers = new Map<string, number>();
  invoices.forEach((invoice) =>
    duplicateInvoiceNumbers.set(
      invoice.canonical_invoice.invoice_number,
      (duplicateInvoiceNumbers.get(invoice.canonical_invoice.invoice_number) ?? 0) + 1
    )
  );

  return invoices
    .map((invoice) => {
      const task = latestTaskByInvoice.get(invoice.invoice_id);
      const invoiceNotifications = notifications.filter((event) => event.invoice_id === invoice.invoice_id);
      const blockedNotification = [...invoiceNotifications]
        .reverse()
        .find((event) => event.notification_type === "invoice_blocked");
      const duplicateLikely = invoiceNotifications.some((event) => event.notification_type === "duplicate_detected");
      const riskLevel =
        typeof blockedNotification?.payload?.risk_level === "string"
          ? blockedNotification.payload.risk_level.replaceAll("_", " ")
          : "not recorded";
      const approvalStatus = task?.status ?? "not routed";
      const poMatchStatus = invoice.canonical_invoice.po_number ? "not recorded" : "missing_po";
      const workflowStatus = workflowStatusFor(task);
      const canDecide = canDecideApproval({ approvalStatus, workflowStatus, riskLevel, poMatchStatus });
      const erpReady = erpReadyFor(task, workflowStatus);
      const blockerReason = task?.reason ?? "No approval task has been created.";
      const dueDate = invoice.canonical_invoice.due_date ?? null;

      return {
        invoice,
        task,
        approvalStatus,
        poMatchStatus,
        workflowStatus,
        riskLevel,
        duplicateLikely:
          duplicateLikely || (duplicateInvoiceNumbers.get(invoice.canonical_invoice.invoice_number) ?? 0) > 1,
        erpReady,
        canDecide,
        blockerReason,
        dueDate,
        isOverdue: isPastDue(dueDate)
      };
    })
    .sort((left, right) => right.invoice.invoice_id.localeCompare(left.invoice.invoice_id));
}

function workflowStatusFor(task: ApprovalTask | undefined) {
  if (!task) return "received";
  if (task.status === "approved" || task.status === "auto_approved") return "approval_ready";
  if (task.status === "rejected") return "rejected";
  if (task.status === "on_hold") return "on_hold";
  if (task.status === "blocked" || task.route === "blocked") return "blocked";
  if (task.status === "pending") return "approval_required";
  return task.status;
}

function erpReadyFor(task: ApprovalTask | undefined, workflowStatus: string) {
  if (!task) return false;
  if (["rejected", "on_hold", "blocked"].includes(task.status)) return false;
  return workflowStatus === "approval_ready";
}

function canDecideApproval(input: {
  approvalStatus: string;
  workflowStatus: string;
  riskLevel: string;
  poMatchStatus: string;
}) {
  if (["approved", "auto_approved", "rejected"].includes(input.approvalStatus)) return false;
  return (
    ["blocked", "approval_required", "on_hold"].includes(input.workflowStatus) ||
    ["high", "critical"].includes(input.riskLevel) ||
    input.poMatchStatus === "missing_po"
  );
}

function matchesFilter(item: ReturnType<typeof buildInboxItems>[number], filter: Filter) {
  switch (filter) {
    case "needs_action":
      return item.canDecide;
    case "blocked":
      return item.workflowStatus === "blocked";
    case "on_hold":
      return item.approvalStatus === "on_hold";
    case "rejected":
      return item.approvalStatus === "rejected";
    case "approval_ready":
      return item.workflowStatus === "approval_ready";
    case "high_risk":
      return ["high", "critical"].includes(item.riskLevel);
    case "missing_po":
      return item.poMatchStatus === "missing_po";
    default:
      return true;
  }
}

function shortId(value: string) {
  return value.slice(-8);
}

function humanize(value: string) {
  return value.replaceAll("_", " ");
}

function money(value: number, currency: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value || 0);
}

function dueDateLabel(value: string | null) {
  if (!value) return "No due date";
  const parsedDate = parseDate(value);
  if (!parsedDate) return "Invalid due date";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric"
  }).format(parsedDate);
}

function dueTone(value: string | null) {
  if (!value) return "text-muted";
  if (!parseDate(value)) return "text-muted";
  const daysUntilDue = daysUntil(value);
  if (daysUntilDue < 0) return "text-danger";
  if (daysUntilDue <= 7) return "text-warning";
  return "text-success";
}

function isPastDue(value: string | null) {
  return value ? daysUntil(value) < 0 : false;
}

function daysUntil(value: string) {
  const today = stripTime(new Date());
  const due = stripTime(parseDate(value) ?? new Date());
  return Math.round((due.getTime() - today.getTime()) / 86_400_000);
}

function stripTime(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function parseDate(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}
