"use client";

import { AlertTriangle, CheckCircle2, ExternalLink, Send } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { apiFetch } from "./frontend-api";

type InvoiceRecord = {
  invoice_id: string;
  canonical_invoice: {
    invoice_number: string;
    supplier_name: string;
    grand_total: number;
    currency: string;
    po_number?: string | null;
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
        `Approval decision saved: ${result.approval_status.replaceAll("_", " ")}. ${
          result.blocker_reason ?? ""
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
      setErpMessage(`Mock ERP export ${result.status}; external ID ${result.external_id ?? "not returned"}.`);
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
      setVendorMessage(`Vendor-safe status refreshed: ${humanize(preview.status)}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Vendor preview failed.");
    }
  }

  return (
    <section className="scroll-mt-6 space-y-3" id="approval-inbox">
      <div>
        <h2 className="text-lg font-semibold">Approval Inbox</h2>
        <p className="text-sm text-muted">Review tenant invoices that need AP attention without using the upload flow.</p>
      </div>

      <div className="rounded-md border border-border bg-white">
        <div className="flex flex-wrap gap-2 border-b border-border px-4 py-3">
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
            <button
              className={`rounded-md border px-3 py-1.5 text-sm ${
                filter === value ? "border-black bg-black text-white" : "border-border"
              }`}
              key={value}
              onClick={() => setFilter(value as Filter)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>

        <div className="grid lg:grid-cols-[minmax(320px,420px)_minmax(0,1fr)] xl:grid-cols-[minmax(360px,420px)_minmax(520px,1fr)]">
          <div className="divide-y divide-border border-b border-border lg:border-b-0 lg:border-r">
            {filteredItems.length ? (
              filteredItems.map((item) => (
                <button
                  className={`grid w-full gap-3 px-4 py-3 text-left text-sm hover:bg-[hsl(var(--background))] sm:grid-cols-[150px_1fr_120px_120px] ${
                    selectedItem?.invoice.invoice_id === item.invoice.invoice_id ? "bg-[hsl(var(--background))]" : ""
                  }`}
                  key={item.invoice.invoice_id}
                  onClick={() => setSelectedInvoiceId(item.invoice.invoice_id)}
                  type="button"
                >
                  <span>
                    <span className="block font-medium">{item.invoice.canonical_invoice.invoice_number}</span>
                    <span className="block text-xs text-muted">#{shortId(item.invoice.invoice_id)}</span>
                  </span>
                  <span>
                    <span className="block">{item.invoice.canonical_invoice.supplier_name}</span>
                    <span className="mt-1 flex flex-wrap gap-1">
                      {item.duplicateLikely ? <Badge label="likely duplicate" tone="warning" /> : null}
                      {item.poMatchStatus === "missing_po" ? <Badge label="missing PO" tone="warning" /> : null}
                      {item.riskLevel !== "not recorded" ? <Badge label={item.riskLevel} tone="warning" /> : null}
                    </span>
                  </span>
                  <span>{money(item.invoice.canonical_invoice.grand_total, item.invoice.canonical_invoice.currency)}</span>
                  <span>
                    <span className="block font-medium">{humanize(item.workflowStatus)}</span>
                    <span className="block text-xs text-muted">{humanize(item.approvalStatus)}</span>
                  </span>
                </button>
              ))
            ) : (
              <div className="px-4 py-8 text-sm text-muted">No invoices match this filter.</div>
            )}
          </div>

          <div className="space-y-5 p-4 lg:p-5">
            {selectedItem ? (
              <>
                <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-lg font-semibold">{selectedItem.invoice.canonical_invoice.invoice_number}</p>
                    <p className="text-sm text-muted">{selectedItem.invoice.canonical_invoice.supplier_name}</p>
                    <p className="mt-2 text-base font-medium">
                      {money(
                        selectedItem.invoice.canonical_invoice.grand_total,
                        selectedItem.invoice.canonical_invoice.currency
                      )}
                    </p>
                    <p className="mt-1 text-xs text-muted">Invoice ID #{shortId(selectedItem.invoice.invoice_id)}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 sm:justify-end">
                    <StatusBadge status={selectedItem.workflowStatus} />
                    {selectedItem.duplicateLikely ? <StatusBadge status="duplicate" /> : null}
                    {erpResult ? <StatusBadge status="exported" /> : null}
                  </div>
                </div>

                <div className="overflow-hidden rounded-md border border-border">
                  <DetailRow label="Workflow" value={<StatusBadge status={selectedItem.workflowStatus} />} />
                  <DetailRow label="Approval" value={<StatusBadge status={selectedItem.approvalStatus} />} />
                  <DetailRow label="PO match" value={<StatusBadge status={selectedItem.poMatchStatus} />} />
                  <DetailRow label="Risk" value={<StatusBadge status={selectedItem.riskLevel} />} />
                  <DetailRow
                    label="ERP ready"
                    value={<StatusBadge status={selectedItem.erpReady ? "erp_ready" : "erp_blocked"} />}
                  />
                  <DetailRow
                    label="Duplicate status"
                    value={<StatusBadge status={selectedItem.duplicateLikely ? "duplicate" : "clear"} />}
                  />
                  <DetailRow
                    label="Vendor-safe status"
                    value={<StatusBadge status={vendorPreview?.status ?? "loading"} />}
                  />
                </div>

                <div className="rounded-md border border-border px-3 py-2 text-sm">
                  <p className="text-xs text-muted">Blocker reason</p>
                  <p className="mt-1">{selectedItem.blockerReason}</p>
                </div>

                <div className="rounded-md border border-border px-3 py-3 text-sm">
                  <p className="mb-2 text-xs text-muted">Vendor-safe preview</p>
                  {vendorPreview ? (
                    <>
                      <p className="font-medium">{humanize(vendorPreview.status)}</p>
                      <p className="mt-1 text-muted">{vendorPreview.public_message}</p>
                    </>
                  ) : (
                    <p className="text-muted">Loading vendor-safe status...</p>
                  )}
                </div>

                {selectedNotifications.length ? (
                  <div className="rounded-md border border-border px-3 py-2 text-sm">
                    <p className="mb-2 text-xs text-muted">Latest notifications</p>
                    <div className="space-y-2">
                      {selectedNotifications.map((event) => (
                        <div key={event.notification_id}>
                          <p className="font-medium">{humanize(event.notification_type)}</p>
                          <p className="text-xs text-muted">
                            {event.recipient_role} - {event.status} via {event.channel}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="grid gap-3 xl:grid-cols-3">
                  <ActionGroup title="Approval actions">
                    {canApproveInvoice && selectedItem.canDecide ? (
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="rounded-md border border-border px-3 py-2 text-sm"
                          disabled={Boolean(activeAction)}
                          onClick={() => void decideApproval("approve")}
                          type="button"
                        >
                          Approve
                        </button>
                        <button
                          className="rounded-md border border-border px-3 py-2 text-sm"
                          disabled={Boolean(activeAction)}
                          onClick={() => void decideApproval("reject")}
                          type="button"
                        >
                          Reject
                        </button>
                        <button
                          className="rounded-md border border-border px-3 py-2 text-sm"
                          disabled={Boolean(activeAction)}
                          onClick={() => void decideApproval("hold")}
                          type="button"
                        >
                          Keep on Hold
                        </button>
                      </div>
                    ) : (
                      <p className="text-sm text-muted">No approval decision is available for this state.</p>
                    )}
                    {approvalMessage ? <p className="text-sm text-green-700">{approvalMessage}</p> : null}
                  </ActionGroup>

                  <ActionGroup title="ERP action">
                    <button
                      className="inline-flex items-center rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
                      disabled={!selectedItem.erpReady || !canExportErp || Boolean(activeAction)}
                      onClick={() => void exportToMockErp()}
                      type="button"
                    >
                      <Send className="mr-2 h-4 w-4" />
                      {activeAction === "export" ? "Exporting..." : "Export to Mock ERP"}
                    </button>
                    {selectedItem.erpReady ? null : (
                      <p className="text-sm text-muted">This invoice is not export-ready yet.</p>
                    )}
                    {erpMessage ? <p className="text-sm text-green-700">{erpMessage}</p> : null}
                  </ActionGroup>

                  <ActionGroup title="Vendor">
                    <button
                      className="inline-flex items-center rounded-md border border-border px-3 py-2 text-sm"
                      disabled={Boolean(activeAction)}
                      onClick={() => void loadVendorPreview(selectedItem.invoice.invoice_id)}
                      type="button"
                    >
                      <ExternalLink className="mr-2 h-4 w-4" />
                      Preview vendor-safe status
                    </button>
                    {vendorMessage ? <p className="text-sm text-green-700">{vendorMessage}</p> : null}
                  </ActionGroup>
                </div>

                {erpResult ? (
                  <div className="rounded-md border border-border px-3 py-2 text-sm">
                    <p className="font-medium">Mock ERP export {erpResult.status}</p>
                    <p className="text-xs text-muted">
                      {erpResult.adapter_type} - {erpResult.external_id ?? "no external id"}
                    </p>
                  </div>
                ) : null}
                {error ? <p className="text-sm text-red-700">{error}</p> : null}
              </>
            ) : (
              <div className="px-1 py-4 text-sm text-muted">No invoice selected.</div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
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
        blockerReason
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

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid gap-2 border-b border-border px-3 py-2 last:border-b-0 sm:grid-cols-[150px_1fr]">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}

function ActionGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-2 rounded-md border border-border px-3 py-3">
      <p className="text-xs text-muted">{title}</p>
      {children}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.replaceAll(" ", "_");
  const tone = badgeTone(normalized);
  const label = humanize(normalized);
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-1 text-xs ${
        tone === "ok"
          ? "border-green-200 bg-green-50 text-green-800"
          : tone === "danger"
            ? "border-red-200 bg-red-50 text-red-800"
            : tone === "muted"
              ? "border-border bg-[hsl(var(--background))] text-muted"
              : "border-amber-200 bg-amber-50 text-amber-800"
      }`}
    >
      {tone === "ok" ? <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> : null}
      {tone === "warning" || tone === "danger" ? <AlertTriangle className="mr-1 h-3.5 w-3.5" /> : null}
      {label}
    </span>
  );
}

function Badge({ label }: { label: string; tone: "ok" | "warning" }) {
  return <StatusBadge status={label} />;
}

function badgeTone(status: string): "ok" | "warning" | "danger" | "muted" {
  if (["approved", "approval_ready", "erp_ready", "clear", "exported"].includes(status)) return "ok";
  if (["rejected"].includes(status)) return "danger";
  if (["blocked", "on_hold", "missing_po", "high", "critical", "duplicate", "erp_blocked"].includes(status)) {
    return "warning";
  }
  return "muted";
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
    maximumFractionDigits: 2
  }).format(value || 0);
}
