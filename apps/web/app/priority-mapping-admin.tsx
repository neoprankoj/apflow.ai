"use client";

import { Braces, Database, RefreshCw, Save, ShieldAlert, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import {
  ApiRequestError,
  generatePriorityPurchaseOrderImportPlan,
  generatePriorityVendorImportPlan,
  getPriorityMapping,
  importPriorityRecords,
  previewPriorityPurchaseOrderSync,
  previewPriorityVendorSync,
  savePriorityMapping,
  type PriorityImportPlanResponse,
  type PriorityImportResult,
  type PriorityMapping,
  type PrioritySyncPreviewKind,
  type PrioritySyncPreviewResponse,
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
  canRunSyncPreview: boolean;
  priorityMode: string;
  tenantId: string | null;
};

export function PriorityMappingAdmin({
  accessToken,
  apiBaseUrl,
  canConfigureErp,
  canRunSyncPreview,
  priorityMode,
  tenantId
}: PriorityMappingAdminProps) {
  const [editorValue, setEditorValue] = useState("");
  const [currentMapping, setCurrentMapping] = useState<PriorityMapping | null>(null);
  const [validation, setValidation] = useState<PriorityMappingValidationResult | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "validating" | "saving">("idle");
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading">("idle");
  const [preview, setPreview] = useState<PrioritySyncPreviewResponse | null>(null);
  const [planStatus, setPlanStatus] = useState<"idle" | "loading">("idle");
  const [importPlan, setImportPlan] = useState<PriorityImportPlanResponse | null>(null);
  const [controlledImportStatus, setControlledImportStatus] = useState<"idle" | "loading">("idle");
  const [controlledImportResult, setControlledImportResult] = useState<PriorityImportResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [previewMessage, setPreviewMessage] = useState<string | null>(null);
  const [planMessage, setPlanMessage] = useState<string | null>(null);
  const [controlledImportMessage, setControlledImportMessage] = useState<string | null>(null);
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

  async function handlePreview(kind: PrioritySyncPreviewKind) {
    if (!apiBaseUrl || !accessToken || !tenantId || !canRunSyncPreview) return;
    setPreviewStatus("loading");
    setPreviewMessage(null);
    try {
      const result =
        kind === "vendors"
          ? await previewPriorityVendorSync(apiBaseUrl, accessToken, tenantId)
          : await previewPriorityPurchaseOrderSync(apiBaseUrl, accessToken, tenantId);
      setPreview(result);
      setPreviewMessage(result.message);
    } catch (error) {
      setPreview(null);
      setPreviewMessage(error instanceof Error ? error.message : "Priority sync preview failed.");
    } finally {
      setPreviewStatus("idle");
    }
  }

  async function handleImportPlan(kind: PrioritySyncPreviewKind) {
    if (!apiBaseUrl || !accessToken || !tenantId || !canRunSyncPreview) return;
    setPlanStatus("loading");
    setPlanMessage(null);
    try {
      const result =
        kind === "vendors"
          ? await generatePriorityVendorImportPlan(apiBaseUrl, accessToken, tenantId)
          : await generatePriorityPurchaseOrderImportPlan(apiBaseUrl, accessToken, tenantId);
      setImportPlan(result);
      setControlledImportResult(null);
      setPlanMessage(result.message);
    } catch (error) {
      setImportPlan(null);
      setPlanMessage(error instanceof Error ? error.message : "Priority import plan failed.");
    } finally {
      setPlanStatus("idle");
    }
  }

  async function handleControlledImport(
    kind: PrioritySyncPreviewKind,
    selectedExternalIds: string[],
    confirmation: string,
    allowCreates: boolean,
    allowUpdates: boolean
  ) {
    if (!apiBaseUrl || !accessToken || !tenantId || !canRunSyncPreview) return;
    setControlledImportStatus("loading");
    setControlledImportMessage(null);
    try {
      const result = await importPriorityRecords(
        apiBaseUrl,
        accessToken,
        tenantId,
        kind,
        selectedExternalIds,
        confirmation,
        allowCreates,
        allowUpdates
      );
      setControlledImportResult(result);
      setControlledImportMessage(result.message);
    } catch (error) {
      setControlledImportResult(null);
      setControlledImportMessage(error instanceof Error ? error.message : "Priority controlled import failed.");
    } finally {
      setControlledImportStatus("idle");
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

              <SyncDryRun
                canRunSyncPreview={canRunSyncPreview}
                controlledImportMessage={controlledImportMessage}
                controlledImportResult={controlledImportResult}
                controlledImportStatus={controlledImportStatus}
                isReady={isReady}
                onControlledImport={handleControlledImport}
                onImportPlan={handleImportPlan}
                onPreview={handlePreview}
                importPlan={importPlan}
                planMessage={planMessage}
                planStatus={planStatus}
                preview={preview}
                previewMessage={previewMessage}
                previewStatus={previewStatus}
              />

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

function SyncDryRun({
  canRunSyncPreview,
  controlledImportMessage,
  controlledImportResult,
  controlledImportStatus,
  importPlan,
  isReady,
  onControlledImport,
  onImportPlan,
  onPreview,
  planMessage,
  planStatus,
  preview,
  previewMessage,
  previewStatus
}: {
  canRunSyncPreview: boolean;
  controlledImportMessage: string | null;
  controlledImportResult: PriorityImportResult | null;
  controlledImportStatus: "idle" | "loading";
  importPlan: PriorityImportPlanResponse | null;
  isReady: boolean;
  onControlledImport: (
    kind: PrioritySyncPreviewKind,
    selectedExternalIds: string[],
    confirmation: string,
    allowCreates: boolean,
    allowUpdates: boolean
  ) => void;
  onImportPlan: (kind: PrioritySyncPreviewKind) => void;
  onPreview: (kind: PrioritySyncPreviewKind) => void;
  planMessage: string | null;
  planStatus: "idle" | "loading";
  preview: PrioritySyncPreviewResponse | null;
  previewMessage: string | null;
  previewStatus: "idle" | "loading";
}) {
  const isVendorPreview = preview?.kind === "vendors";
  const [selectedExternalIds, setSelectedExternalIds] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState("");
  const [allowCreates, setAllowCreates] = useState(true);
  const [allowUpdates, setAllowUpdates] = useState(false);
  const selectedItems = useMemo(
    () =>
      (importPlan?.items ?? []).filter((item) =>
        selectedExternalIds.includes(String(item.mapped_record.external_id ?? ""))
      ),
    [importPlan, selectedExternalIds]
  );
  const selectedCreates = selectedItems.filter((item) => item.action === "would_create").length;
  const selectedUpdates = selectedItems.filter((item) => item.action === "would_update").length;

  useEffect(() => {
    setSelectedExternalIds([]);
    setConfirmation("");
  }, [importPlan]);

  function toggleSelectedExternalId(externalId: string) {
    setSelectedExternalIds((current) =>
      current.includes(externalId)
        ? current.filter((value) => value !== externalId)
        : [...current, externalId]
    );
  }

  function runControlledImport() {
    if (!importPlan) return;
    onControlledImport(importPlan.kind, selectedExternalIds, confirmation, allowCreates, allowUpdates);
  }

  return (
    <div className="space-y-4 rounded-md border border-border bg-slate-50 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-primary" />
            <h4 className="font-semibold">Sync Dry Run</h4>
          </div>
          <p className="mt-1 text-sm text-muted">
            Preview how saved Priority mappings transform vendor and purchase-order records. Dry run only:
            no records are imported and no ERP data is changed.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!isReady || !canRunSyncPreview || previewStatus !== "idle"}
            onClick={() => onPreview("vendors")}
            variant="secondary"
          >
            Preview Vendor Sync
          </Button>
          <Button
            disabled={!isReady || !canRunSyncPreview || previewStatus !== "idle"}
            onClick={() => onPreview("purchase_orders")}
            variant="secondary"
          >
            Preview Purchase Orders
          </Button>
        </div>
      </div>

      {!canRunSyncPreview ? (
        <div className="rounded-md border border-border bg-white px-4 py-3 text-sm text-muted">
          You do not have permission to run ERP sync previews.
        </div>
      ) : null}

      {previewStatus === "loading" ? (
        <div className="space-y-2">
          <LoadingSkeleton className="h-8 w-full" />
          <LoadingSkeleton className="h-24 w-full" />
        </div>
      ) : null}

      {previewMessage ? (
        <div className="rounded-md border border-border bg-white px-4 py-3 text-sm text-muted">
          {previewMessage}
        </div>
      ) : null}

      {preview ? (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={preview.status} />
            <StatusBadge status={`source: ${preview.source}`} />
            <StatusBadge status={`mode: ${preview.mode}`} />
            <StatusBadge status={`mapping: ${preview.mapping_status}`} />
            <StatusBadge status={`${preview.records_previewed} rows`} />
          </div>
          {preview.errors.length ? <ValidationList label="Preview errors" items={preview.errors} tone="danger" /> : null}
          {preview.warnings.length ? <ValidationList label="Preview warnings" items={preview.warnings} tone="warning" /> : null}
          {preview.status === "preview_ready" ? (
            <PreviewTable
              columns={
                isVendorPreview
                  ? ["external_id", "name", "tax_id", "email", "payment_terms"]
                  : ["po_number", "vendor_external_id", "status", "total_amount", "currency"]
              }
              records={preview.mapped_records}
            />
          ) : null}
        </div>
      ) : null}

      <div className="space-y-4 rounded-md border border-border bg-white p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h4 className="font-semibold">Import Plan</h4>
            <p className="mt-1 text-sm text-muted">
              Compare mapped Priority rows against APFlow data before any import path is enabled.
              Planning only: no records are imported into APFlow and no ERP data is changed.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!isReady || !canRunSyncPreview || planStatus !== "idle"}
              onClick={() => onImportPlan("vendors")}
              variant="secondary"
            >
              Generate Vendor Import Plan
            </Button>
            <Button
              disabled={!isReady || !canRunSyncPreview || planStatus !== "idle"}
              onClick={() => onImportPlan("purchase_orders")}
              variant="secondary"
            >
              Generate Purchase Order Import Plan
            </Button>
          </div>
        </div>

        {planStatus === "loading" ? (
          <div className="space-y-2">
            <LoadingSkeleton className="h-8 w-full" />
            <LoadingSkeleton className="h-24 w-full" />
          </div>
        ) : null}

        {planMessage ? (
          <div className="rounded-md border border-border bg-slate-50 px-4 py-3 text-sm text-muted">
            {planMessage}
          </div>
        ) : null}

        {importPlan ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <StatusBadge status={importPlan.status} />
              <StatusBadge status={`source: ${importPlan.source}`} />
              <StatusBadge status={`mode: ${importPlan.mode}`} />
              <StatusBadge status={`${importPlan.records_planned} planned`} />
            </div>
            <PlanSummary summary={importPlan.summary} />
            {importPlan.errors.length ? <ValidationList label="Plan errors" items={importPlan.errors} tone="danger" /> : null}
            {importPlan.warnings.length ? <ValidationList label="Plan warnings" items={importPlan.warnings} tone="warning" /> : null}
            {importPlan.status === "plan_ready" ? (
              <>
                <ImportPlanTable
                  columns={
                    importPlan.kind === "vendors"
                      ? ["select", "action", "external_id", "name", "matched_existing_id", "reason", "warnings"]
                      : ["select", "action", "po_number", "vendor_external_id", "total_amount", "matched_existing_id", "reason", "warnings"]
                  }
                  items={importPlan.items}
                  onToggleSelected={toggleSelectedExternalId}
                  selectedExternalIds={selectedExternalIds}
                />
                <ControlledImportControls
                  allowCreates={allowCreates}
                  allowUpdates={allowUpdates}
                  confirmation={confirmation}
                  controlledImportMessage={controlledImportMessage}
                  controlledImportResult={controlledImportResult}
                  controlledImportStatus={controlledImportStatus}
                  disabled={!isReady || !canRunSyncPreview || controlledImportStatus !== "idle"}
                  onAllowCreatesChange={setAllowCreates}
                  onAllowUpdatesChange={setAllowUpdates}
                  onConfirmationChange={setConfirmation}
                  onImport={runControlledImport}
                  selectedCount={selectedExternalIds.length}
                  selectedCreates={selectedCreates}
                  selectedUpdates={selectedUpdates}
                />
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function PreviewTable({
  columns,
  records
}: {
  columns: string[];
  records: Record<string, unknown>[];
}) {
  if (!records.length) {
    return (
      <EmptyState
        description="Run a dry-run preview after saving a mapping to inspect transformed records."
        title="No preview rows"
      />
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border border-border bg-white">
      <table className="min-w-full divide-y divide-border text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            {columns.map((column) => (
              <th className="px-3 py-2 font-medium" key={column}>
                {labelFor(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {records.map((record, index) => (
            <tr className="hover:bg-slate-50" key={`${record.external_id ?? record.po_number ?? index}`}>
              {columns.map((column) => (
                <td className="px-3 py-2 text-foreground" key={column}>
                  {formatValue(record[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlanSummary({ summary }: { summary: Record<string, number> }) {
  const entries = ["would_create", "would_update", "would_skip", "would_conflict"];
  return (
    <div className="grid gap-2 text-sm sm:grid-cols-4">
      {entries.map((key) => (
        <div className="rounded-md border border-border bg-slate-50 p-3" key={key}>
          <p className="text-xs uppercase tracking-wide text-muted">{labelFor(key)}</p>
          <p className="mt-1 text-lg font-semibold">{summary[key] ?? 0}</p>
        </div>
      ))}
    </div>
  );
}

function ImportPlanTable({
  columns,
  items,
  onToggleSelected,
  selectedExternalIds
}: {
  columns: string[];
  items: PriorityImportPlanResponse["items"];
  onToggleSelected: (externalId: string) => void;
  selectedExternalIds: string[];
}) {
  if (!items.length) {
    return (
      <EmptyState
        description="Generate an import plan after saving a mapping to compare mapped rows with APFlow records."
        title="No planned rows"
      />
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border border-border bg-white">
      <table className="min-w-full divide-y divide-border text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            {columns.map((column) => (
              <th className="px-3 py-2 font-medium" key={column}>
                {labelFor(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((item, index) => (
            <tr className="hover:bg-slate-50" key={`${item.action}-${item.mapped_record.external_id ?? index}`}>
              {columns.map((column) => (
                <td className="px-3 py-2 align-top text-foreground" key={column}>
                  {renderPlanCell(item, column, selectedExternalIds, onToggleSelected)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderPlanCell(
  item: PriorityImportPlanResponse["items"][number],
  column: string,
  selectedExternalIds: string[],
  onToggleSelected: (externalId: string) => void
) {
  const externalId = String(item.mapped_record.external_id ?? "");
  const importable = item.action === "would_create" || item.action === "would_update";
  if (column === "select") {
    return (
      <input
        aria-label={`Select ${externalId || "Priority row"}`}
        checked={Boolean(externalId && selectedExternalIds.includes(externalId))}
        className="h-4 w-4 rounded border-border text-primary"
        disabled={!externalId || !importable}
        onChange={() => onToggleSelected(externalId)}
        type="checkbox"
      />
    );
  }
  if (column === "action") return <StatusBadge status={item.action} />;
  if (column === "matched_existing_id") return item.matched_existing_id ? shortId(item.matched_existing_id) : "-";
  if (column === "reason") return <span className="max-w-sm text-muted">{item.reason}</span>;
  if (column === "warnings") return item.warnings.length ? item.warnings.join("; ") : "-";
  return formatValue(item.mapped_record[column]);
}

function ControlledImportControls({
  allowCreates,
  allowUpdates,
  confirmation,
  controlledImportMessage,
  controlledImportResult,
  controlledImportStatus,
  disabled,
  onAllowCreatesChange,
  onAllowUpdatesChange,
  onConfirmationChange,
  onImport,
  selectedCount,
  selectedCreates,
  selectedUpdates
}: {
  allowCreates: boolean;
  allowUpdates: boolean;
  confirmation: string;
  controlledImportMessage: string | null;
  controlledImportResult: PriorityImportResult | null;
  controlledImportStatus: "idle" | "loading";
  disabled: boolean;
  onAllowCreatesChange: (value: boolean) => void;
  onAllowUpdatesChange: (value: boolean) => void;
  onConfirmationChange: (value: string) => void;
  onImport: () => void;
  selectedCount: number;
  selectedCreates: number;
  selectedUpdates: number;
}) {
  const canImport = !disabled && selectedCount > 0 && confirmation === "IMPORT_SELECTED";
  return (
    <div className="space-y-4 rounded-md border border-border bg-slate-50 p-4">
      <div>
        <h5 className="font-semibold">Controlled Import</h5>
        <p className="mt-1 text-sm text-muted">
          Imports selected records into APFlow only. No data is written to Priority. Conflicts are never imported,
          and updates require explicit enablement.
        </p>
      </div>
      <div className="grid gap-3 text-sm md:grid-cols-3">
        <Detail label="Selected rows" value={String(selectedCount)} />
        <Detail label="Creates selected" value={String(selectedCreates)} />
        <Detail label="Updates selected" value={String(selectedUpdates)} />
      </div>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input checked={allowCreates} onChange={(event) => onAllowCreatesChange(event.target.checked)} type="checkbox" />
          Allow creates
        </label>
        <label className="flex items-center gap-2">
          <input checked={allowUpdates} onChange={(event) => onAllowUpdatesChange(event.target.checked)} type="checkbox" />
          Allow updates
        </label>
      </div>
      <label className="block text-sm">
        <span className="font-medium">Type IMPORT_SELECTED to enable import</span>
        <input
          className="mt-2 w-full rounded-md border border-border px-3 py-2"
          onChange={(event) => onConfirmationChange(event.target.value)}
          placeholder="IMPORT_SELECTED"
          value={confirmation}
        />
      </label>
      <Button disabled={!canImport} onClick={onImport} variant="primary">
        {controlledImportStatus === "loading" ? "Importing..." : "Import Selected"}
      </Button>
      {controlledImportMessage ? (
        <div className="rounded-md border border-border bg-white px-4 py-3 text-sm text-muted">
          {controlledImportMessage}
        </div>
      ) : null}
      {controlledImportResult ? <ControlledImportResult result={controlledImportResult} /> : null}
    </div>
  );
}

function ControlledImportResult({ result }: { result: PriorityImportResult }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <StatusBadge status={result.status} />
        {Object.entries(result.summary).map(([key, value]) => (
          <StatusBadge key={key} status={`${labelFor(key)}: ${value}`} />
        ))}
      </div>
      {result.errors.length ? <ValidationList label="Import errors" items={result.errors} tone="danger" /> : null}
      {result.warnings.length ? <ValidationList label="Import warnings" items={result.warnings} tone="warning" /> : null}
      <div className="overflow-x-auto rounded-md border border-border bg-white">
        <table className="min-w-full divide-y divide-border text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              {["result", "external_id", "apflow_record_id", "reason", "warnings"].map((column) => (
                <th className="px-3 py-2 font-medium" key={column}>
                  {labelFor(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {result.items.map((item, index) => (
              <tr className="hover:bg-slate-50" key={`${item.external_id ?? "item"}-${index}`}>
                <td className="px-3 py-2 align-top"><StatusBadge status={item.result} /></td>
                <td className="px-3 py-2 align-top">{item.external_id ?? "-"}</td>
                <td className="px-3 py-2 align-top">{item.apflow_record_id ? shortId(item.apflow_record_id) : "-"}</td>
                <td className="px-3 py-2 align-top text-muted">{item.reason}</td>
                <td className="px-3 py-2 align-top">{item.warnings.length ? item.warnings.join("; ") : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
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

function labelFor(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(value);
}

function shortId(value: string) {
  return value.length > 8 ? value.slice(0, 8) : value;
}
