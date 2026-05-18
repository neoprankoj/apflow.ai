"use client";

import { Braces, RefreshCw, Save, ShieldAlert, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import {
  ApiRequestError,
  getPriorityMapping,
  savePriorityMapping,
  type PriorityMapping,
  type PriorityMappingValidationResult,
  validatePriorityMapping
} from "./frontend-api";

const SAMPLE_MAPPING: PriorityMapping = {
  version: "1",
  vendors: {
    enabled: true,
    entity_name: "SUPPLIERS",
    external_id_field: "SUPNAME",
    fields: {
      name: "SUPDES",
      tax_id: "VATNUM",
      email: "EMAIL",
      payment_terms: "PAYCODE"
    }
  },
  purchase_orders: {
    enabled: true,
    entity_name: "PORDERS",
    external_id_field: "ORDNAME",
    fields: {
      po_number: "ORDNAME",
      vendor_external_id: "SUPNAME",
      status: "ORDSTATUSDES",
      total_amount: "TOTPRICE",
      currency: "CODE"
    }
  },
  invoice_export: {
    enabled: true,
    entity_name: "APINVOICES",
    external_id_field: "IVNUM",
    fields: {
      invoice_number: "IVNUM",
      invoice_date: "IVDATE",
      vendor_external_id: "SUPNAME",
      total_amount: "TOTPRICE",
      currency: "CODE",
      description: "DETAILS"
    }
  }
};

type PriorityMappingAdminProps = {
  accessToken: string | null;
  apiBaseUrl: string | null;
  canConfigureErp: boolean;
  priorityMode: string;
  tenantId: string | null;
};

export function PriorityMappingAdmin({
  accessToken,
  apiBaseUrl,
  canConfigureErp,
  priorityMode,
  tenantId
}: PriorityMappingAdminProps) {
  const [editorValue, setEditorValue] = useState("");
  const [currentMapping, setCurrentMapping] = useState<PriorityMapping | null>(null);
  const [validation, setValidation] = useState<PriorityMappingValidationResult | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "validating" | "saving">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [localJsonError, setLocalJsonError] = useState<string | null>(null);

  const isReady = Boolean(apiBaseUrl && accessToken && tenantId);
  const mappingStatus = useMemo(() => {
    if (validation) return validation.status;
    return currentMapping ? "configured" : "not configured";
  }, [currentMapping, validation]);
  const editorIsValidJson = useMemo(() => {
    if (!editorValue) return false;
    try {
      JSON.parse(editorValue);
      return true;
    } catch {
      return false;
    }
  }, [editorValue]);

  const loadMapping = useCallback(async () => {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setStatus("loading");
    setMessage(null);
    try {
      const response = await getPriorityMapping(apiBaseUrl, accessToken, tenantId);
      setCurrentMapping(response.mapping);
      setEditorValue(response.mapping ? formatJson(response.mapping) : "");
      setLocalJsonError(null);
      if (response.mapping && canConfigureErp) {
        const result = await validatePriorityMapping(apiBaseUrl, accessToken, tenantId, response.mapping);
        setValidation(result);
      } else {
        setValidation(null);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Priority mapping failed to load.");
    } finally {
      setStatus("idle");
    }
  }, [accessToken, apiBaseUrl, canConfigureErp, tenantId]);

  useEffect(() => {
    void loadMapping();
  }, [loadMapping]);

  function parseEditorValue() {
    try {
      const parsed = JSON.parse(editorValue) as PriorityMapping;
      setLocalJsonError(null);
      return parsed;
    } catch {
      setLocalJsonError("Invalid JSON. Check commas, quotes, and braces before continuing.");
      return null;
    }
  }

  async function handleValidate() {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    const parsed = parseEditorValue();
    if (!parsed) return;
    setStatus("validating");
    setMessage(null);
    try {
      const result = await validatePriorityMapping(apiBaseUrl, accessToken, tenantId, parsed);
      setValidation(result);
      setMessage("Validation completed. Review any warnings before saving.");
    } catch (error) {
      setValidation(null);
      setMessage(error instanceof Error ? error.message : "Priority mapping validation failed.");
    } finally {
      setStatus("idle");
    }
  }

  async function handleSave() {
    if (!apiBaseUrl || !accessToken || !tenantId || !canConfigureErp) return;
    const parsed = parseEditorValue();
    if (!parsed) return;
    setStatus("saving");
    setMessage(null);
    try {
      await savePriorityMapping(apiBaseUrl, accessToken, tenantId, parsed);
      setMessage("Priority mapping saved successfully.");
      await loadMapping();
    } catch (error) {
      if (error instanceof ApiRequestError) {
        setMessage(error.message);
      } else {
        setMessage("Priority mapping save failed.");
      }
    } finally {
      setStatus("idle");
    }
  }

  function loadSample() {
    setEditorValue(formatJson(SAMPLE_MAPPING));
    setValidation(null);
    setMessage("Sample mapping loaded. Verify every entity and field against the customer's Priority environment.");
    setLocalJsonError(null);
  }

  return (
    <section className="scroll-mt-6 space-y-3" id="admin">
      <div>
        <h2 className="text-lg font-semibold">Admin</h2>
        <p className="text-sm text-muted">Tenant-scoped ERP configuration and staging-safe controls.</p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 border-b border-border lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Braces className="h-4 w-4 text-primary" />
              <h3 className="text-base font-semibold">Priority ERP Mapping</h3>
            </div>
            <p className="mt-1 max-w-2xl text-sm text-muted">
              Configure how customer-specific Priority OData entities map to APFlow vendors, purchase orders, and invoice export fields.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={priorityMode || "mock"} />
            <StatusBadge status={mappingStatus} />
            <StatusBadge status="writes disabled" />
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          <div className="grid gap-3 rounded-md border border-border bg-background p-4 text-sm md:grid-cols-3">
            <Detail label="Priority mode" value={priorityMode || "mock"} />
            <Detail label="Tenant" value={tenantId ?? "Sign in required"} />
            <Detail label="Real writes" value="Disabled by default" />
          </div>

          <div className="grid gap-3 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-slate-700">
            <p>Mock Priority remains the active staging mode unless `PRIORITY_ERP_MODE` is changed.</p>
            <p>Real Priority writes are disabled unless `PRIORITY_ERP_ENABLE_WRITES=true`.</p>
            <p>Validate mappings before enabling any real sync/export. Do not paste credentials into this JSON.</p>
          </div>

          {!isReady ? (
            <EmptyState
              description="Sign in before loading tenant ERP configuration."
              icon={ShieldAlert}
              title="Priority mapping is unavailable"
            />
          ) : status === "loading" ? (
            <div className="space-y-3">
              <LoadingSkeleton className="h-10 w-full" />
              <LoadingSkeleton className="h-72 w-full" />
            </div>
          ) : (
            <>
              {!canConfigureErp ? (
                <div className="rounded-md border border-border bg-slate-50 px-4 py-3 text-sm text-muted">
                  You do not have permission to update ERP mappings.
                </div>
              ) : null}

              <label className="block space-y-2">
                <span className="text-sm font-medium">Mapping JSON</span>
                <textarea
                  className="min-h-[320px] w-full resize-y rounded-md border border-border bg-white p-4 font-mono text-sm text-foreground shadow-sm outline-none focus:border-primary"
                  onChange={(event) => {
                    setEditorValue(event.target.value);
                    setValidation(null);
                    setLocalJsonError(null);
                  }}
                  placeholder="Paste tenant-specific Priority mapping JSON here."
                  readOnly={!canConfigureErp}
                  value={editorValue}
                />
              </label>

              {!currentMapping && !editorValue ? (
                <EmptyState
                  description="No Priority mapping is configured for this tenant yet. Load the sample to start from a safe template."
                  icon={Braces}
                  title="No mapping configured"
                />
              ) : null}

              {localJsonError ? (
                <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
                  {localJsonError}
                </div>
              ) : null}

              {message ? <div className="rounded-md border border-border px-4 py-3 text-sm text-muted">{message}</div> : null}

              {validation ? <ValidationSummary validation={validation} /> : null}

              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={!isReady || status !== "idle"}
                  onClick={() => void loadMapping()}
                  variant="secondary"
                >
                  <RefreshCw className="h-4 w-4" />
                  Reload
                </Button>
                <Button disabled={!canConfigureErp || status !== "idle"} onClick={loadSample} variant="ghost">
                  <Wand2 className="h-4 w-4" />
                  Reset to sample
                </Button>
                <Button
                  disabled={!canConfigureErp || !editorValue || status !== "idle"}
                  onClick={() => void handleValidate()}
                  variant="secondary"
                >
                  Validate
                </Button>
                <Button
                  disabled={!canConfigureErp || !editorIsValidJson || status !== "idle"}
                  onClick={() => void handleSave()}
                  variant="primary"
                >
                  <Save className="h-4 w-4" />
                  Save mapping
                </Button>
              </div>

              <p className="text-xs text-muted">
                Sample only - verify entity and field names against the customer&apos;s Priority environment.
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function ValidationSummary({ validation }: { validation: PriorityMappingValidationResult }) {
  return (
    <div className="space-y-3 rounded-md border border-border bg-slate-50 p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Validation result</span>
        <StatusBadge status={validation.status} />
      </div>
      {validation.errors.length ? <ValidationList label="Errors" items={validation.errors} tone="danger" /> : null}
      {validation.warnings.length ? <ValidationList label="Warnings" items={validation.warnings} tone="warning" /> : null}
      <div>
        <p className="font-medium">Summary</p>
        <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-white p-3 text-xs text-muted">
          {formatJson(validation.summary)}
        </pre>
      </div>
    </div>
  );
}

function ValidationList({
  label,
  items,
  tone
}: {
  label: string;
  items: string[];
  tone: "danger" | "warning";
}) {
  return (
    <div>
      <p className="font-medium">{label}</p>
      <ul className={tone === "danger" ? "mt-2 space-y-1 text-danger" : "mt-2 space-y-1 text-warning"}>
        {items.map((item) => (
          <li key={item}>- {item}</li>
        ))}
      </ul>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-medium">{value}</p>
    </div>
  );
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}
