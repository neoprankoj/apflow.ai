"use client";

import { FileCheck2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import {
  ComplianceProfileRead,
  ComplianceSummary,
  InvoiceComplianceResult,
  getComplianceSummary,
  getInvoiceCompliance,
  listComplianceProfiles
} from "./frontend-api";

type ComplianceInvoice = {
  invoice_id: string;
  canonical_invoice: {
    invoice_number: string;
    supplier_name: string;
    grand_total: number;
    currency: string;
  };
};

export function CompliancePanel({
  accessToken,
  apiBaseUrl,
  invoices,
  tenantId
}: {
  accessToken: string | null;
  apiBaseUrl: string | null;
  invoices: ComplianceInvoice[];
  tenantId: string | null;
}) {
  const [profiles, setProfiles] = useState<ComplianceProfileRead[]>([]);
  const [selectedProfile, setSelectedProfile] = useState("generic_b2b");
  const [summary, setSummary] = useState<ComplianceSummary | null>(null);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [invoiceResult, setInvoiceResult] = useState<InvoiceComplianceResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedProfileDetails = useMemo(
    () => profiles.find((profile) => profile.key === selectedProfile),
    [profiles, selectedProfile]
  );
  const selectedInvoice = useMemo(
    () => invoices.find((invoice) => invoice.invoice_id === selectedInvoiceId) ?? invoices[0] ?? null,
    [invoices, selectedInvoiceId]
  );

  const load = useCallback(async () => {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setIsLoading(true);
    setError(null);
    try {
      const loadedProfiles = await listComplianceProfiles(apiBaseUrl, accessToken);
      setProfiles(loadedProfiles);
      const profileKey = loadedProfiles.some((profile) => profile.key === selectedProfile)
        ? selectedProfile
        : loadedProfiles[0]?.key ?? "generic_b2b";
      setSelectedProfile(profileKey);
      setSummary(await getComplianceSummary(apiBaseUrl, accessToken, tenantId, profileKey));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Compliance validation could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, apiBaseUrl, selectedProfile, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedInvoiceId && invoices[0]) {
      setSelectedInvoiceId(invoices[0].invoice_id);
    }
  }, [invoices, selectedInvoiceId]);

  async function handleProfileChange(profileKey: string) {
    setSelectedProfile(profileKey);
    setInvoiceResult(null);
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setIsLoading(true);
    setError(null);
    try {
      setSummary(await getComplianceSummary(apiBaseUrl, accessToken, tenantId, profileKey));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Compliance summary could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }

  async function validateSelectedInvoice() {
    if (!apiBaseUrl || !accessToken || !tenantId || !selectedInvoice) return;
    setIsValidating(true);
    setError(null);
    try {
      setInvoiceResult(
        await getInvoiceCompliance(apiBaseUrl, accessToken, tenantId, selectedInvoice.invoice_id, selectedProfile)
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invoice compliance validation failed.");
    } finally {
      setIsValidating(false);
    }
  }

  return (
    <section className="scroll-mt-6 space-y-4" id="e-invoicing-compliance">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold">E-Invoicing Compliance</h2>
          <p className="mt-1 text-sm text-muted">
            Validation-only checks for required invoice data. No government, tax authority, PEPPOL, or e-invoicing network submission is performed.
          </p>
        </div>
        <Button disabled={!tenantId || isLoading} onClick={() => void load()} variant="secondary">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}

      {isLoading && !summary ? (
        <div className="grid gap-3 md:grid-cols-4">
          {[0, 1, 2, 3].map((item) => <LoadingSkeleton className="h-24 w-full" key={item} />)}
        </div>
      ) : (
        <>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <FileCheck2 className="h-4 w-4 text-primary" />
                <h3 className="text-base font-semibold">Validation Profile</h3>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <select
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm md:max-w-sm"
                onChange={(event) => void handleProfileChange(event.target.value)}
                value={selectedProfile}
              >
                {profiles.map((profile) => (
                  <option key={profile.key} value={profile.key}>{profile.label}</option>
                ))}
              </select>
              {selectedProfileDetails ? (
                <div className="rounded-md border border-border p-3 text-sm">
                  <p className="font-medium">{selectedProfileDetails.country_or_region}</p>
                  <p className="mt-1 text-muted">{selectedProfileDetails.description}</p>
                  <p className="mt-2 text-xs text-muted">
                    Validation only. Certified integration: {selectedProfileDetails.certified_integration ? "yes" : "no"}.
                  </p>
                </div>
              ) : null}
            </CardContent>
          </Card>

          {summary ? (
            <div className="grid gap-3 md:grid-cols-4">
              <SummaryCard label="Checked" value={summary.total_checked} status="neutral" />
              <SummaryCard label="Ready" value={summary.compliant_count} status="pass" />
              <SummaryCard label="Needs Review" value={summary.needs_review_count} status="warning" />
              <SummaryCard label="Not Compliant" value={summary.not_compliant_count} status="fail" />
            </div>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-[1fr_1.3fr]">
            <Card>
              <CardHeader>
                <h3 className="text-base font-semibold">Invoice Compliance List</h3>
              </CardHeader>
              <CardContent className="space-y-3">
                {invoices.length ? invoices.map((invoice) => (
                  <button
                    className={`w-full rounded-md border p-3 text-left text-sm transition ${
                      selectedInvoice?.invoice_id === invoice.invoice_id
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/60"
                    }`}
                    key={invoice.invoice_id}
                    onClick={() => {
                      setSelectedInvoiceId(invoice.invoice_id);
                      setInvoiceResult(null);
                    }}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{invoice.canonical_invoice.invoice_number}</p>
                        <p className="text-muted">{invoice.canonical_invoice.supplier_name}</p>
                      </div>
                      <p className="font-semibold">
                        {invoice.canonical_invoice.currency} {invoice.canonical_invoice.grand_total.toFixed(2)}
                      </p>
                    </div>
                  </button>
                )) : (
                  <EmptyState
                    description="Upload and process invoices before running e-invoicing readiness checks."
                    title="Process invoices to run compliance validation"
                  />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="text-base font-semibold">Validation Details</h3>
                  <p className="text-sm text-muted">View required fields, warnings, and next steps for the selected invoice.</p>
                </div>
                <Button disabled={!selectedInvoice || isValidating} onClick={() => void validateSelectedInvoice()}>
                  Validate Invoice
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                {invoiceResult ? (
                  <>
                    <div className="rounded-md border border-border p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{invoiceResult.summary}</p>
                          <p className="mt-1 text-xs text-muted">{invoiceResult.legal_disclaimer}</p>
                        </div>
                        <StatusBadge status={invoiceResult.status} />
                      </div>
                    </div>
                    <div className="space-y-2">
                      {invoiceResult.checks.map((check) => (
                        <div className="rounded-md border border-border p-3 text-sm" key={check.key}>
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="font-medium">{check.label}</p>
                              <p className="mt-1 text-muted">{check.message}</p>
                              {check.next_step ? <p className="mt-1 text-xs text-muted">Next: {check.next_step}</p> : null}
                            </div>
                            <StatusBadge status={check.status} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <EmptyState
                    description="Select an invoice and run validation to see required fields, warnings, and next steps."
                    title="No invoice validation selected"
                  />
                )}
              </CardContent>
            </Card>
          </div>

          {summary && Object.keys(summary.common_missing_fields).length ? (
            <Card>
              <CardHeader>
                <h3 className="text-base font-semibold">Common Missing Fields</h3>
              </CardHeader>
              <CardContent className="grid gap-2 md:grid-cols-3">
                {Object.entries(summary.common_missing_fields).map(([field, count]) => (
                  <div className="rounded-md border border-border p-3 text-sm" key={field}>
                    <p className="font-medium">{humanize(field)}</p>
                    <p className="text-muted">{count} invoice{count === 1 ? "" : "s"}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </>
      )}
    </section>
  );
}

function SummaryCard({ label, status, value }: { label: string; status: string; value: number }) {
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm text-muted">{label}</p>
          <StatusBadge status={status} />
        </div>
        <p className="text-3xl font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
