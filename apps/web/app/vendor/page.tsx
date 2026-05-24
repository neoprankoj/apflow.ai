"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, FileText, MessageCircle, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/empty-state";
import { LoadingSkeleton } from "../../components/ui/loading-skeleton";
import { StatusBadge } from "../../components/ui/status-badge";
import {
  ApiRequestError,
  getApiBaseUrl,
  getVendorInvoicePreview,
  listVendorInvoices,
  vendorChat,
  type VendorChatResponse,
  type VendorInvoiceListItem,
  type VendorInvoiceStatus
} from "../frontend-api";

export default function VendorPortalPage() {
  const apiBaseUrl = getApiBaseUrl();
  const query = useQueryValues();
  const tenantId = query.get("tenant_id");
  const accessToken = query.get("access_token");
  const [invoices, setInvoices] = useState<VendorInvoiceListItem[]>([]);
  const [selectedInvoice, setSelectedInvoice] = useState<VendorInvoiceStatus | null>(null);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatResponse, setChatResponse] = useState<VendorChatResponse | null>(null);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canLoad = Boolean(apiBaseUrl && tenantId && accessToken);

  const loadInvoices = useCallback(async () => {
    if (!apiBaseUrl || !tenantId || !accessToken) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await listVendorInvoices(apiBaseUrl, tenantId, accessToken);
      setInvoices(result);
      if (result.length > 0) {
        setSelectedInvoiceId((current) => current ?? result[0].invoice_id);
      }
    } catch (err) {
      setError(readVendorError(err));
      setInvoices([]);
      setSelectedInvoice(null);
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, apiBaseUrl, tenantId]);

  useEffect(() => {
    if (canLoad) void loadInvoices();
  }, [canLoad, loadInvoices]);

  useEffect(() => {
    async function loadDetail() {
      if (!apiBaseUrl || !tenantId || !accessToken || !selectedInvoiceId) return;
      setIsDetailLoading(true);
      setError(null);
      try {
        const result = await getVendorInvoicePreview(apiBaseUrl, tenantId, accessToken, selectedInvoiceId);
        setSelectedInvoice(result);
      } catch (err) {
        setError(readVendorError(err));
        setSelectedInvoice(null);
      } finally {
        setIsDetailLoading(false);
      }
    }
    void loadDetail();
  }, [accessToken, apiBaseUrl, selectedInvoiceId, tenantId]);

  const selectedListItem = useMemo(
    () => invoices.find((invoice) => invoice.invoice_id === selectedInvoiceId) ?? null,
    [invoices, selectedInvoiceId]
  );

  async function handleChatSubmit(questionOverride?: string) {
    const question = (questionOverride ?? chatQuestion).trim();
    if (!apiBaseUrl || !tenantId || !accessToken || !question) return;
    setIsChatLoading(true);
    setChatError(null);
    try {
      const result = await vendorChat(apiBaseUrl, tenantId, accessToken, question, {
        invoiceId: selectedInvoice?.invoice_id ?? selectedInvoiceId ?? undefined,
        invoiceNumber: selectedInvoice?.invoice_number ?? selectedListItem?.invoice_number ?? undefined
      });
      setChatQuestion(question);
      setChatResponse(result);
    } catch (err) {
      setChatError(readVendorError(err));
      setChatResponse(null);
    } finally {
      setIsChatLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto max-w-5xl space-y-5">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-primary">
              <ShieldCheck className="h-4 w-4" />
              APFlow Vendor Portal
            </div>
            <h1 className="mt-2 text-2xl font-semibold">Supplier invoice status</h1>
            <p className="mt-1 max-w-2xl text-sm text-muted">
              This page shows vendor-safe invoice and payment status only. Internal AP review notes, risk details, audit logs, and ERP configuration are never shown here.
            </p>
          </div>
          <Button disabled={!canLoad || isLoading} onClick={() => void loadInvoices()} variant="secondary">
            <RefreshCw className="h-4 w-4" />
            Reload
          </Button>
        </header>

        {!apiBaseUrl ? (
          <StateCard title="Vendor portal is not configured" description="The frontend API URL is missing. Contact APFlow support or AP operations." />
        ) : !tenantId || !accessToken ? (
          <StateCard title="Vendor access link is incomplete" description="Open the complete vendor access link provided by AP. It should include both tenant and access token values." />
        ) : error ? (
          <StateCard title="Vendor access unavailable" description={error} />
        ) : null}

        {canLoad && !error ? (
          <div className="grid gap-5 lg:grid-cols-[minmax(320px,420px)_1fr]">
            <Card>
              <CardHeader>
                <h2 className="text-base font-semibold">Invoices</h2>
                <p className="mt-1 text-sm text-muted">Only invoices that match this supplier access are listed.</p>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="space-y-2">
                    <LoadingSkeleton className="h-16" />
                    <LoadingSkeleton className="h-16" />
                    <LoadingSkeleton className="h-16" />
                  </div>
                ) : invoices.length ? (
                  <div className="space-y-2">
                    {invoices.map((invoice) => (
                      <button
                        className={`w-full rounded-md border px-3 py-3 text-left transition-colors ${
                          selectedInvoiceId === invoice.invoice_id
                            ? "border-primary bg-blue-50"
                            : "border-border bg-surface hover:bg-slate-50"
                        }`}
                        key={invoice.invoice_id}
                        onClick={() => setSelectedInvoiceId(invoice.invoice_id)}
                        type="button"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium">{invoice.invoice_number}</p>
                            <p className="text-sm text-muted">{invoice.supplier_name}</p>
                          </div>
                          <StatusBadge status={invoice.status} />
                        </div>
                        <div className="mt-3 flex items-center justify-between gap-3 text-sm">
                          <span>{formatDate(invoice.invoice_date)}</span>
                          <span className="font-semibold">{formatMoney(invoice.grand_total, invoice.currency)}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    description="This token is valid, but no vendor-visible invoices currently match this supplier. Ask AP to confirm the supplier name or invoice status."
                    title="No vendor-visible invoices"
                  />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <h2 className="text-base font-semibold">Invoice preview</h2>
                <p className="mt-1 text-sm text-muted">Safe invoice status and payment information for the selected invoice.</p>
              </CardHeader>
              <CardContent>
                {isDetailLoading ? (
                  <div className="space-y-3">
                    <LoadingSkeleton className="h-8" />
                    <LoadingSkeleton className="h-20" />
                    <LoadingSkeleton className="h-20" />
                  </div>
                ) : selectedInvoice ? (
                  <div className="space-y-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm text-muted">Invoice</p>
                        <h3 className="text-xl font-semibold">{selectedInvoice.invoice_number}</h3>
                        <p className="text-sm text-muted">{selectedInvoice.supplier_name}</p>
                      </div>
                      <StatusBadge status={selectedInvoice.status} />
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <Detail label="Amount" value={formatMoney(selectedInvoice.grand_total, selectedInvoice.currency)} />
                      <Detail label="Invoice date" value={formatDate(selectedInvoice.invoice_date)} />
                      <Detail label="Due date" value={formatDate(selectedInvoice.due_date)} />
                      <Detail label="Line items" value={String(selectedInvoice.line_item_count)} />
                    </div>

                    <section className="rounded-md border border-border p-4">
                      <p className="text-sm font-semibold">Status message</p>
                      <p className="mt-1 text-sm text-muted">{selectedInvoice.public_message}</p>
                    </section>

                    {selectedInvoice.payment_status_detail ? (
                      <section className="rounded-md border border-border p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold">Payment status</p>
                            <p className="mt-1 text-sm text-muted">{selectedInvoice.payment_status_detail.safe_message}</p>
                          </div>
                          <StatusBadge status={selectedInvoice.payment_status_detail.status} />
                        </div>
                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                          <Detail label="Amount due" value={formatOptionalMoney(selectedInvoice.payment_status_detail.amount_due, selectedInvoice.payment_status_detail.currency)} />
                          <Detail label="Amount paid" value={formatOptionalMoney(selectedInvoice.payment_status_detail.amount_paid, selectedInvoice.payment_status_detail.currency)} />
                          <Detail label="Scheduled date" value={formatDate(selectedInvoice.payment_status_detail.scheduled_payment_date)} />
                          <Detail label="Paid date" value={formatDate(selectedInvoice.payment_status_detail.paid_at)} />
                        </div>
                      </section>
                    ) : (
                      <section className="rounded-md border border-border p-4">
                        <p className="text-sm font-semibold">Payment status</p>
                        <p className="mt-1 text-sm text-muted">Payment status is not available yet.</p>
                      </section>
                    )}
                  </div>
                ) : selectedListItem ? (
                  <EmptyState
                    description="Select the invoice again or reload the page."
                    icon={FileText}
                    title="Invoice preview could not be loaded"
                  />
                ) : (
                  <EmptyState
                    description="Choose an invoice from the list to view vendor-safe details."
                    icon={FileText}
                    title="No invoice selected"
                  />
                )}
              </CardContent>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <MessageCircle className="h-4 w-4 text-primary" />
                  <h2 className="text-base font-semibold">Ask about payment status</h2>
                </div>
                <p className="mt-1 text-sm text-muted">
                  This assistant only answers vendor-safe invoice and payment-status questions. It cannot show internal AP notes, audit logs, ERP details, risk scores, or token details.
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  {exampleQuestions(selectedInvoice?.invoice_number ?? selectedListItem?.invoice_number).map((question) => (
                    <Button
                      disabled={isChatLoading}
                      key={question}
                      onClick={() => void handleChatSubmit(question)}
                      size="sm"
                      variant="secondary"
                    >
                      {question}
                    </Button>
                  ))}
                </div>

                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    className="min-h-10 flex-1 rounded-md border border-border px-3 py-2 text-sm"
                    onChange={(event) => setChatQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void handleChatSubmit();
                    }}
                    placeholder="Ask about invoice or payment status"
                    value={chatQuestion}
                  />
                  <Button disabled={isChatLoading || !chatQuestion.trim()} onClick={() => void handleChatSubmit()} variant="primary">
                    <Send className="h-4 w-4" />
                    Ask
                  </Button>
                </div>

                {chatError ? (
                  <p className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">{chatError}</p>
                ) : null}

                {chatResponse ? (
                  <div className="rounded-md border border-border p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="text-sm font-semibold">Answer</p>
                      <StatusBadge status={chatResponse.refused ? "refused" : chatResponse.intent} />
                    </div>
                    <p className="mt-2 text-sm text-muted">{chatResponse.answer}</p>
                    {chatResponse.matched_invoices.length ? (
                      <div className="mt-4 grid gap-2 sm:grid-cols-2">
                        {chatResponse.matched_invoices.slice(0, 4).map((invoice) => (
                          <div className="rounded-md border border-border p-3 text-sm" key={invoice.invoice_id}>
                            <p className="font-medium">{invoice.invoice_number}</p>
                            <p className="text-muted">{invoice.supplier_name}</p>
                            <p className="mt-1">{formatMoney(invoice.grand_total, invoice.currency)}</p>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        ) : null}
      </div>
    </main>
  );
}

function useQueryValues() {
  const [params, setParams] = useState<URLSearchParams>(() => new URLSearchParams());
  useEffect(() => {
    setParams(new URLSearchParams(window.location.search));
  }, []);
  return params;
}

function StateCard({ description, title }: { description: string; title: string }) {
  return (
    <Card>
      <CardContent>
        <EmptyState description={description} icon={AlertTriangle} title={title} />
      </CardContent>
    </Card>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs uppercase text-muted">{label}</p>
      <p className="mt-1 font-semibold">{value}</p>
    </div>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function formatMoney(value: number, currency: string) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value);
}

function formatOptionalMoney(value: number | null | undefined, currency: string) {
  if (value === null || value === undefined) return "Not available";
  return formatMoney(value, currency);
}

function readVendorError(error: unknown) {
  if (error instanceof ApiRequestError) {
    if (error.status === 401 || error.status === 403) {
      return "This vendor access link is invalid, expired, or revoked. Ask AP for a new access link.";
    }
    return error.detail ?? error.message;
  }
  if (error instanceof Error) return error.message;
  return "Vendor invoices could not be loaded.";
}

function exampleQuestions(invoiceNumber?: string | null) {
  const number = invoiceNumber ?? "40100";
  return [
    `What is the status of invoice ${number}?`,
    "Which invoices are pending?",
    "Has this invoice been paid?",
    "When is payment scheduled?"
  ];
}
