"use client";

import { RefreshCw, WalletCards } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import {
  getPaymentSummary,
  listPaymentStatuses,
  PaymentStatusRead,
  PaymentStatusSummary,
  runMockPaymentSync,
  updatePaymentStatus
} from "./frontend-api";

type InvoiceOption = {
  invoice_id: string;
  canonical_invoice: {
    invoice_number: string;
    supplier_name: string;
    grand_total: number;
    currency: string;
  };
};

const statusOptions = [
  "not_started",
  "pending",
  "scheduled",
  "partially_paid",
  "paid",
  "failed",
  "disputed",
  "cancelled",
  "unknown"
];

export function PaymentStatusPanel({
  accessToken,
  apiBaseUrl,
  canUpdatePaymentStatus,
  invoices,
  tenantId
}: {
  accessToken: string | null;
  apiBaseUrl: string | null;
  canUpdatePaymentStatus: boolean;
  invoices: InvoiceOption[];
  tenantId: string | null;
}) {
  const [statuses, setStatuses] = useState<PaymentStatusRead[]>([]);
  const [summary, setSummary] = useState<PaymentStatusSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedStatusId, setSelectedStatusId] = useState<string>("");
  const [manualStatus, setManualStatus] = useState("scheduled");
  const [amountPaid, setAmountPaid] = useState("");
  const [safeMessage, setSafeMessage] = useState("");

  const load = useCallback(async () => {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [loadedStatuses, loadedSummary] = await Promise.all([
        listPaymentStatuses(apiBaseUrl, accessToken, tenantId),
        getPaymentSummary(apiBaseUrl, accessToken, tenantId)
      ]);
      setStatuses(loadedStatuses);
      setSummary(loadedSummary);
      setSelectedStatusId((current) => current || loadedStatuses[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment status refresh failed.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, apiBaseUrl, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const invoiceById = useMemo(
    () => new Map(invoices.map((invoice) => [invoice.invoice_id, invoice])),
    [invoices]
  );

  async function handleMockSync() {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setActionMessage(null);
    setError(null);
    try {
      const result = await runMockPaymentSync(apiBaseUrl, accessToken, tenantId);
      setActionMessage(`Mock payment sync updated ${result.length} ${result.length === 1 ? "invoice" : "invoices"}. No bank or ERP payment system was contacted.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mock payment sync failed.");
    }
  }

  async function handleManualUpdate() {
    if (!apiBaseUrl || !accessToken || !tenantId || !selectedStatusId) return;
    setActionMessage(null);
    setError(null);
    try {
      await updatePaymentStatus(apiBaseUrl, accessToken, tenantId, selectedStatusId, {
        status: manualStatus,
        amount_paid: amountPaid ? Number(amountPaid) : null,
        safe_vendor_message: safeMessage || null
      });
      setActionMessage("Payment status updated. Vendors only see the safe payment message, not internal AP notes.");
      setAmountPaid("");
      setSafeMessage("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment status update failed.");
    }
  }

  const summaryCards = [
    { label: "Pending", value: summary?.pending_count ?? 0, status: "pending" },
    { label: "Scheduled", value: summary?.scheduled_count ?? 0, status: "scheduled" },
    { label: "Paid", value: summary?.paid_count ?? 0, status: "paid" },
    { label: "Failed / Disputed", value: summary?.failed_or_disputed_count ?? 0, status: "failed" }
  ];

  return (
    <section className="scroll-mt-6 space-y-4" id="payment-status">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Payment Status</h2>
          <p className="mt-1 text-sm text-muted">
            Track invoice payment lifecycle inside APFlow. This foundation is manual/mock only; no bank or real ERP payment sync runs here.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!tenantId || isLoading} onClick={() => void load()} variant="secondary">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button disabled={!canUpdatePaymentStatus || !tenantId || isLoading} onClick={() => void handleMockSync()} variant="primary">
            <WalletCards className="h-4 w-4" />
            Run Mock Payment Sync
          </Button>
        </div>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}
      {actionMessage ? <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{actionMessage}</div> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map((item) => (
          <Card key={item.label}>
            <CardContent className="space-y-2">
              <StatusBadge status={item.status} />
              <p className="text-2xl font-semibold">{item.value}</p>
              <p className="text-sm text-muted">{item.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <h3 className="text-base font-semibold">Invoice Payment List</h3>
            <p className="mt-1 text-sm text-muted">Vendor-safe payment status can be shown in Vendor Preview when available.</p>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-3 p-5">
                {[0, 1, 2].map((item) => <LoadingSkeleton className="h-14 w-full" key={item} />)}
              </div>
            ) : statuses.length ? (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-border bg-slate-50 text-xs uppercase text-muted">
                    <tr>
                      <th className="px-4 py-3">Invoice</th>
                      <th className="px-4 py-3">Supplier</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3 text-right">Due</th>
                      <th className="px-4 py-3 text-right">Paid</th>
                      <th className="px-4 py-3">Source</th>
                      <th className="px-4 py-3">Last synced</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {statuses.map((item) => {
                      const invoice = invoiceById.get(item.invoice_id);
                      return (
                        <tr className="hover:bg-slate-50" key={item.id}>
                          <td className="px-4 py-3 font-medium">{invoice?.canonical_invoice.invoice_number ?? shortId(item.invoice_id)}</td>
                          <td className="px-4 py-3">{invoice?.canonical_invoice.supplier_name ?? "Unknown supplier"}</td>
                          <td className="px-4 py-3"><StatusBadge status={item.status} /></td>
                          <td className="px-4 py-3 text-right">{money(item.amount_due, item.currency)}</td>
                          <td className="px-4 py-3 text-right">{money(item.amount_paid, item.currency)}</td>
                          <td className="px-4 py-3"><StatusBadge status={item.source} /></td>
                          <td className="px-4 py-3 text-muted">{formatDate(item.last_synced_at ?? item.updated_at)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-5">
                <EmptyState
                  description={
                    tenantId
                      ? "Payment statuses will appear after invoices are approved/exported or after mock payment sync."
                      : "Sign in to load tenant payment statuses."
                  }
                  title="No payment statuses yet"
                />
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h3 className="text-base font-semibold">Manual Update</h3>
            <p className="mt-1 text-sm text-muted">Update APFlow payment state only. Vendors see safe payment copy, not internal notes.</p>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="block text-sm font-medium">
              Payment record
              <select
                className="mt-1 h-10 w-full rounded-md border border-border bg-white px-3 text-sm"
                disabled={!canUpdatePaymentStatus || !statuses.length}
                onChange={(event) => setSelectedStatusId(event.target.value)}
                value={selectedStatusId}
              >
                {statuses.map((item) => {
                  const invoice = invoiceById.get(item.invoice_id);
                  return (
                    <option key={item.id} value={item.id}>
                      {invoice?.canonical_invoice.invoice_number ?? shortId(item.invoice_id)} - {item.status}
                    </option>
                  );
                })}
              </select>
            </label>
            <label className="block text-sm font-medium">
              Status
              <select
                className="mt-1 h-10 w-full rounded-md border border-border bg-white px-3 text-sm"
                disabled={!canUpdatePaymentStatus || !statuses.length}
                onChange={(event) => setManualStatus(event.target.value)}
                value={manualStatus}
              >
                {statusOptions.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
              </select>
            </label>
            <label className="block text-sm font-medium">
              Amount paid
              <input
                className="mt-1 h-10 w-full rounded-md border border-border bg-white px-3 text-sm"
                disabled={!canUpdatePaymentStatus || !statuses.length}
                onChange={(event) => setAmountPaid(event.target.value)}
                placeholder="0.00"
                type="number"
                value={amountPaid}
              />
            </label>
            <label className="block text-sm font-medium">
              Safe vendor message
              <textarea
                className="mt-1 min-h-20 w-full rounded-md border border-border bg-white px-3 py-2 text-sm"
                disabled={!canUpdatePaymentStatus || !statuses.length}
                onChange={(event) => setSafeMessage(event.target.value)}
                placeholder="Optional safe message shown in Vendor Preview"
                value={safeMessage}
              />
            </label>
            <Button
              className="w-full"
              disabled={!canUpdatePaymentStatus || !selectedStatusId}
              onClick={() => void handleManualUpdate()}
              variant="primary"
            >
              Update Payment Status
            </Button>
            {!canUpdatePaymentStatus ? (
              <p className="text-xs text-muted">You can view payment statuses, but you do not have permission to update them.</p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function money(value: number | null | undefined, currency = "USD") {
  if (value == null) return "Not set";
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value);
}

function formatDate(value: string | null | undefined) {
  if (!value) return "Not synced";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Not synced";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(parsed);
}

function shortId(value: string) {
  return value.slice(0, 8);
}
