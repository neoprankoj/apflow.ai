"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Play,
  ScanText,
  Send,
  UploadCloud
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AuthStatus, apiFetch } from "./frontend-api";
import { TimelineStage, WorkflowTimeline } from "./workflow-timeline";

type UploadedDocument = {
  document_id: string;
  original_file_name: string;
  content_type: string;
  size_bytes: number;
  storage_provider: string;
};

type UploadResult = {
  document: UploadedDocument;
};

type ConfidenceSummary = {
  average_confidence: number;
  high_confidence_fields: number;
  medium_confidence_fields: number;
  low_confidence_fields: number;
  required_fields_missing?: string[];
  required_fields_low_confidence?: string[];
};

type ExtractedField = {
  field_name: string;
  value: string | number | null;
  confidence: number;
  raw_text?: string | null;
  requires_review?: boolean;
};

type OcrResult = {
  fields?: ExtractedField[];
  provider_metadata?: {
    provider_name?: string;
    raw_provider_status?: string | null;
    parsed_result_count?: number | null;
    parsed_text_length?: number | null;
    ocr_exit_code?: string | number | null;
    detected_content_type?: string | null;
    sent_file_name?: string | null;
    sent_filetype?: string | null;
    sent_content_type?: string | null;
    provider_error_message?: string | null;
  };
  raw_response?: {
    provider?: string;
    parsed_result_count?: number;
    parsed_text_length?: number;
    ocr_text_preview?: string;
    ocr_exit_code?: string | number | null;
    detected_content_type?: string | null;
    sent_file_name?: string | null;
    sent_filetype?: string | null;
    sent_content_type?: string | null;
    provider_error_message?: string | null;
    is_errored_on_processing?: boolean;
  };
  error?: string | null;
};

type ReviewIssue = {
  field_name: string;
  message: string;
  issue_type?: string;
  confidence?: number;
  current_value?: string | number | null;
};

type ReviewTask = {
  task_id: string;
  status: string;
  issues?: ReviewIssue[];
  corrected_fields?: Record<string, string | number>;
};

type ExtractResult = {
  confidence_summary?: ConfidenceSummary;
  review_status?: string;
  review_tasks?: ReviewTask[];
  ocr_result?: OcrResult;
};

type PipelineResult = {
  invoice?: {
    invoice_id: string;
    canonical_invoice?: {
      invoice_number: string;
      supplier_name: string;
      grand_total: number;
      currency: string;
    };
  } | null;
  validation_result?: { validation_status: string } | null;
  duplicate_result?: { status: string } | null;
  po_match_result?: { match_status: string } | null;
  fraud_risk_result?: { risk_level: string } | null;
  approval_result?: { route: string; assigned_role?: string; approval_status?: string; reason?: string } | null;
  erp_export_ready?: boolean;
  confidence_summary?: ConfidenceSummary;
  ocr_result?: OcrResult;
  review_tasks?: ReviewTask[];
  corrected_fields_applied?: boolean;
  corrected_field_count?: number;
  unresolved_review_fields?: string[];
  invoice_created?: boolean;
  blocker_reason?: string | null;
};

type ProcessResult = {
  workflow_status: string;
  review_status: string;
  pipeline_result?: PipelineResult;
  corrected_fields_applied?: boolean;
  corrected_field_count?: number;
  unresolved_review_fields?: string[];
  invoice_created?: boolean;
  blocker_reason?: string | null;
};

type ERPSyncResult = {
  sync_id: string;
  adapter_type: string;
  operation: string;
  status: string;
  external_id: string | null;
  records_processed: number;
  errors: string[];
  details: Record<string, unknown>;
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
  invoice_id: string;
  approval_task_id: string;
  action: "approve" | "reject" | "hold";
  route: string;
  approval_status: string;
  reason: string;
  workflow_status: string;
  erp_export_ready: boolean;
  blocker_reason?: string | null;
};

type StepStatus = "pending" | "active" | "completed" | "failed";

type Props = {
  accessToken: string | null;
  apiBaseUrl: string | null;
  authStatus: AuthStatus;
  tenantId: string | null;
  selectedOcrProvider?: string;
  selectedOcrStatus?: string;
  canExportErp?: boolean;
  canApproveInvoice?: boolean;
  canCorrectReview?: boolean;
  resetSignal?: number;
  onDemoLogin: () => void;
  onWorkflowUpdated?: () => Promise<void> | void;
};

const REQUIRED_CORRECTION_FIELDS = ["invoice_number", "supplier_name", "invoice_date", "currency", "grand_total"];

export function InvoiceUploadPanel({
  accessToken,
  apiBaseUrl,
  authStatus,
  tenantId,
  selectedOcrProvider = "mock",
  selectedOcrStatus = "ok",
  canExportErp = true,
  canApproveInvoice = false,
  canCorrectReview = false,
  resetSignal = 0,
  onDemoLogin,
  onWorkflowUpdated
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [extractResult, setExtractResult] = useState<ExtractResult | null>(null);
  const [processResult, setProcessResult] = useState<ProcessResult | null>(null);
  const [erpResult, setErpResult] = useState<ERPSyncResult | null>(null);
  const [erpLogs, setErpLogs] = useState<ERPSyncResult[]>([]);
  const [vendorPreview, setVendorPreview] = useState<VendorInvoiceStatus | null>(null);
  const [approvalDecision, setApprovalDecision] = useState<ApprovalDecisionResult | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [activeAction, setActiveAction] = useState<
    "upload" | "extract" | "process" | "export" | "vendor-preview" | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [correctionMessage, setCorrectionMessage] = useState<string | null>(null);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [timestamps, setTimestamps] = useState<Record<string, string>>({});

  const documentId = uploadResult?.document.document_id;
  const pipeline = processResult?.pipeline_result;
  const invoice = pipeline?.invoice?.canonical_invoice;
  const invoiceId = pipeline?.invoice?.invoice_id;
  const confidence = pipeline?.confidence_summary ?? extractResult?.confidence_summary;
  const ocrResult = pipeline?.ocr_result ?? extractResult?.ocr_result;
  const ocrRawResponse = ocrResult?.raw_response;
  const ocrProviderMetadata = ocrResult?.provider_metadata;
  const ocrTextPreview = ocrRawResponse?.ocr_text_preview;
  const parsedTextLength =
    ocrRawResponse?.parsed_text_length ?? ocrProviderMetadata?.parsed_text_length ?? 0;
  const parsedResultCount =
    ocrRawResponse?.parsed_result_count ?? ocrProviderMetadata?.parsed_result_count ?? 0;
  const sentFileName = ocrRawResponse?.sent_file_name ?? ocrProviderMetadata?.sent_file_name ?? "n/a";
  const sentFiletype = ocrRawResponse?.sent_filetype ?? ocrProviderMetadata?.sent_filetype ?? "n/a";
  const sentContentType =
    ocrRawResponse?.sent_content_type ?? ocrProviderMetadata?.sent_content_type ?? "n/a";
  const providerErrorMessage =
    ocrRawResponse?.provider_error_message ?? ocrProviderMetadata?.provider_error_message ?? ocrResult?.error;
  const fileTypeAdvice =
    providerErrorMessage &&
    /file type|file extension|e216|unable to recognize/i.test(providerErrorMessage)
      ? "OCR.space could not detect file type. Try a real exported PDF/image or check filetype configuration."
      : null;
  const fields = ocrResult?.fields ?? [];
  const reviewRequiredFields = Array.from(
    new Set([
      ...fields.filter((field) => field.requires_review).map((field) => field.field_name),
      ...(confidence?.required_fields_missing ?? []),
      ...(confidence?.required_fields_low_confidence ?? [])
    ])
  );
  const invoiceCreated = processResult?.invoice_created ?? pipeline?.invoice_created ?? Boolean(invoiceId);
  const approvalDisplayStatus = pipeline?.approval_result?.approval_status ?? pipeline?.approval_result?.route;
  const erpExportReady = Boolean(pipeline?.erp_export_ready);
  const approvalNeedsAction = shouldShowApprovalDecisionActions({
    invoiceCreated,
    invoiceId,
    workflowStatus: processResult?.workflow_status,
    approvalRoute: pipeline?.approval_result?.route,
    approvalStatus: pipeline?.approval_result?.approval_status
  });
  const blockedWithoutCurrentInvoice =
    isBlockedApprovalState({
      workflowStatus: processResult?.workflow_status,
      approvalRoute: pipeline?.approval_result?.route,
      approvalStatus: pipeline?.approval_result?.approval_status
    }) && (!invoiceCreated || !invoiceId);
  const blockerReason = processResult?.blocker_reason ?? pipeline?.blocker_reason;
  const selectedFileName = useMemo(() => file?.name ?? "No file selected", [file]);
  const isSignedIn = authStatus === "authenticated" && Boolean(accessToken && tenantId);
  const signInRequired = !isSignedIn;
  const isBusy = activeAction !== null;
  const reviewStatus = processResult?.review_status ?? extractResult?.review_status;
  const reviewTasks = processResult ? pipeline?.review_tasks ?? [] : extractResult?.review_tasks ?? [];
  const reviewIssues = reviewTasks.flatMap((task) => task.issues ?? []);
  const correctedIssueFields = new Set(
    reviewTasks.flatMap((task) => Object.keys(task.corrected_fields ?? {}))
  );
  const visibleReviewIssues = reviewIssues.filter((issue) => !correctedIssueFields.has(issue.field_name));
  const resolvedReviewFields = fields
    .filter((field) => !field.requires_review && field.value !== null && field.value !== undefined && field.value !== "")
    .map((field) => field.field_name);
  const correctionFields = Array.from(
    new Set(
      [
        ...(reviewTasks.length ? REQUIRED_CORRECTION_FIELDS : []),
        ...reviewIssues.map((issue) => issue.field_name),
        ...(confidence?.required_fields_missing ?? []),
        ...(confidence?.required_fields_low_confidence ?? [])
      ].filter((fieldName) => fieldName !== "document")
    )
  );
  const correctionDefaults = useMemo(
    () => buildCorrectionDefaults(correctionFields, fields, reviewIssues, reviewTasks),
    [correctionFields.join("|"), fields, reviewIssues, reviewTasks]
  );
  const demoSteps = buildDemoSteps({
    signedIn: isSignedIn,
    file,
    uploadResult,
    extractResult,
    processResult,
    erpResult,
    vendorPreview,
    status,
    error,
    erpExportReady
  });
  const timelineStages = buildTimeline({
    uploadResult,
    extractResult,
    processResult,
    erpResult,
    timestamps
  });

  useEffect(() => {
    if (!correctionFields.length) return;
    setCorrections((current) => {
      const next = { ...current };
      let changed = false;
      for (const fieldName of correctionFields) {
        if (next[fieldName] === undefined && correctionDefaults[fieldName] !== undefined) {
          next[fieldName] = correctionDefaults[fieldName];
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [correctionDefaults, correctionFields]);

  useEffect(() => {
    if (!resetSignal) return;
    setFile(null);
    setUploadResult(null);
    setExtractResult(null);
    setProcessResult(null);
    setErpResult(null);
    setErpLogs([]);
    setVendorPreview(null);
    setApprovalDecision(null);
    setStatus("idle");
    setActiveAction(null);
    setError(null);
    setCorrectionMessage(null);
    setCorrections({});
    setTimestamps({});
  }, [resetSignal]);

  function walkthroughAction(label: string) {
    if (signInRequired) {
      return { label: "Demo login", action: onDemoLogin, disabled: authStatus === "authenticating" };
    }
    if (label === "Step 2") {
      return { label: activeAction === "upload" ? "Uploading..." : "Upload", action: upload, disabled: !file || Boolean(uploadResult) || isBusy };
    }
    if (label === "Step 3") {
      return { label: activeAction === "extract" ? "Extracting..." : "Extract", action: extractOnly, disabled: !documentId || isBusy };
    }
    if (label === "Step 4") {
      return { label: activeAction === "process" ? "Processing..." : "Process", action: processPipeline, disabled: !documentId || isBusy };
    }
    if (label === "Step 6") {
      return { label: activeAction === "export" ? "Exporting..." : "Export", action: exportToMockErp, disabled: !canExportErp || !erpExportReady || Boolean(erpResult) || isBusy };
    }
    if (label === "Step 7") {
      return { label: activeAction === "vendor-preview" ? "Loading..." : "Preview", action: loadVendorPreview, disabled: !invoiceId || isBusy };
    }
    return null;
  }

  async function upload() {
    if (!ensureSignedIn()) return;
    const requestContext = getSignedInRequestContext();
    if (!requestContext) return;
    if (!file) {
      setError("Select a PDF or image first.");
      return;
    }
    setError(null);
    setStatus("uploading");
    setActiveAction("upload");
    const form = new FormData();
    form.append("tenant_id", requestContext.tenantId);
    form.append("file", file);
    try {
      const result = await apiFetch<UploadResult>(requestContext.apiBaseUrl, "/documents/invoices/upload", {
        method: "POST",
        body: form,
        token: requestContext.accessToken,
        action: "Upload invoice"
      });
      setUploadResult(result);
      setExtractResult(null);
      setProcessResult(null);
      setErpResult(null);
      setVendorPreview(null);
      setApprovalDecision(null);
      mark("uploaded");
      setStatus("uploaded");
    } catch (error) {
      setStatus("failed");
      setError(error instanceof Error ? error.message : "Upload failed: API unavailable.");
    } finally {
      setActiveAction(null);
    }
  }

  async function extractOnly() {
    if (!ensureSignedIn()) return;
    const requestContext = getSignedInRequestContext();
    if (!requestContext) return;
    if (!documentId) return;
    setError(null);
    setStatus("extracting");
    setActiveAction("extract");
    try {
      const result = await apiFetch<ExtractResult>(
        requestContext.apiBaseUrl,
        `/documents/invoices/${documentId}/extract?tenant_id=${requestContext.tenantId}`,
        { method: "POST", token: requestContext.accessToken, action: "Extract invoice" }
      );
      setExtractResult(result);
      setCorrections({});
      setCorrectionMessage(null);
      mark("extracted");
      setStatus(result.review_status === "review_required" ? "review_required" : "extracted");
    } catch (error) {
      setStatus("failed");
      setError(error instanceof Error ? error.message : "Extraction failed because the API is unavailable.");
    } finally {
      setActiveAction(null);
    }
  }

  async function processPipeline() {
    if (!ensureSignedIn()) return;
    const requestContext = getSignedInRequestContext();
    if (!requestContext) return;
    if (!documentId) return;
    setError(null);
    setStatus("processing");
    setActiveAction("process");
    try {
      const result = await apiFetch<ProcessResult>(requestContext.apiBaseUrl, `/documents/invoices/${documentId}/process`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ tenant_id: requestContext.tenantId }),
        token: requestContext.accessToken,
        action: "Process invoice"
      });
      setProcessResult(result);
      setApprovalDecision(null);
      mark("processed");
      setStatus(result.workflow_status);
    } catch (error) {
      setStatus("failed");
      setError(error instanceof Error ? error.message : "Processing failed because the API is unavailable.");
    } finally {
      setActiveAction(null);
    }
  }

  async function submitCorrections() {
    if (!ensureSignedIn()) return;
    const requestContext = getSignedInRequestContext();
    if (!requestContext) return;
    const task = reviewTasks.find((item) => item.status === "review_required") ?? reviewTasks[0];
    if (!task) {
      setCorrectionMessage("No review task is available for this extraction.");
      return;
    }
    const cleanCorrections = Object.fromEntries(
      Object.entries(corrections)
        .map(([fieldName, value]) => [fieldName, value.trim()])
        .filter(([, value]) => value)
    );
    if (!Object.keys(cleanCorrections).length) {
      setCorrectionMessage("Enter at least one corrected field before submitting.");
      return;
    }
    setError(null);
    setCorrectionMessage("Submitting corrections...");
    setActiveAction("process");
    try {
      const result = await apiFetch<{ task_id: string; status: string; corrected_fields: Record<string, string | number> }>(
        requestContext.apiBaseUrl,
        `/review/tasks/${task.task_id}/corrections`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            tenant_id: requestContext.tenantId,
            corrections: cleanCorrections,
            reviewer_id: "dashboard-demo"
          }),
          token: requestContext.accessToken,
          action: "Submit review corrections"
        }
      );
      const correctedStrings = stringifyCorrections(result.corrected_fields);
      setCorrections((current) => ({ ...current, ...correctedStrings }));
      setExtractResult((current) =>
        current
          ? {
              ...current,
              review_status: result.status,
              review_tasks: (current.review_tasks ?? []).map((item) =>
                item.task_id === result.task_id
                  ? { ...item, status: result.status, corrected_fields: result.corrected_fields }
                  : item
              ),
              ocr_result: current.ocr_result
                ? {
                    ...current.ocr_result,
                    fields: mergeCorrectedFields(current.ocr_result.fields ?? [], result.corrected_fields)
                  }
                : current.ocr_result
            }
          : current
      );
      setProcessResult((current) =>
        current?.pipeline_result
          ? {
              ...current,
              review_status: result.status,
              pipeline_result: {
                ...current.pipeline_result,
                review_tasks: (current.pipeline_result.review_tasks ?? []).map((item) =>
                  item.task_id === result.task_id
                    ? { ...item, status: result.status, corrected_fields: result.corrected_fields }
                    : item
                ),
                ocr_result: current.pipeline_result.ocr_result
                  ? {
                      ...current.pipeline_result.ocr_result,
                      fields: mergeCorrectedFields(current.pipeline_result.ocr_result.fields ?? [], result.corrected_fields)
                    }
                  : current.pipeline_result.ocr_result
              }
            }
          : current
      );
      setCorrectionMessage("Corrections saved. Click Process to continue.");
    } catch (error) {
      setCorrectionMessage(error instanceof Error ? error.message : "Correction submission failed.");
    } finally {
      setActiveAction(null);
    }
  }

  async function exportToMockErp() {
    if (!ensureSignedIn()) return;
    const requestContext = getSignedInRequestContext();
    if (!requestContext) return;
    if (!invoiceId || !erpExportReady || !canExportErp) return;
    setError(null);
    setStatus("exporting");
    setActiveAction("export");
    try {
      const result = await apiFetch<ERPSyncResult>(requestContext.apiBaseUrl, "/erp/export-invoice", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          tenant_id: requestContext.tenantId,
          adapter_type: "priority",
          invoice_id: invoiceId
        }),
        token: requestContext.accessToken,
        action: "Export invoice to ERP"
      });
      setErpResult(result);
      mark("exported_to_erp");
      setStatus("exported");
      const logs = await apiFetch<ERPSyncResult[]>(requestContext.apiBaseUrl, `/erp/sync-logs?tenant_id=${requestContext.tenantId}`, {
        token: requestContext.accessToken,
        action: "Load ERP sync logs"
      });
      setErpLogs(logs.slice(-3).reverse());
    } catch (error) {
      setStatus("failed");
      setError(error instanceof Error ? error.message : "ERP export failed because the API is unavailable.");
    } finally {
      setActiveAction(null);
    }
  }

  async function loadVendorPreview() {
    if (!ensureSignedIn()) return;
    const requestContext = getSignedInRequestContext();
    if (!requestContext) return;
    if (!invoiceId) return;
    setError(null);
    setStatus("loading vendor preview");
    setActiveAction("vendor-preview");
    try {
      const preview = await apiFetch<VendorInvoiceStatus>(
        requestContext.apiBaseUrl,
        `/vendor/preview/invoices/${invoiceId}?tenant_id=${requestContext.tenantId}`,
        {
          token: requestContext.accessToken,
          action: "Load vendor-safe status"
        }
      );
      setVendorPreview(preview);
      mark("vendor_preview");
      setStatus("vendor preview ready");
    } catch (error) {
      setStatus("failed");
      setError(error instanceof Error ? error.message : "Vendor preview failed because the API is unavailable.");
    } finally {
      setActiveAction(null);
    }
  }

  async function decideApproval(action: ApprovalDecisionResult["action"]) {
    if (!ensureSignedIn()) return;
    const requestContext = getSignedInRequestContext();
    if (!requestContext || !invoiceId || !canApproveInvoice) return;
    setError(null);
    setStatus(`approval ${action}`);
    setActiveAction("process");
    try {
      const result = await apiFetch<ApprovalDecisionResult>(
        requestContext.apiBaseUrl,
        `/invoices/${invoiceId}/approval-decision`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            tenant_id: requestContext.tenantId,
            action
          }),
          token: requestContext.accessToken,
          action: `${action} invoice`
        }
      );
      setApprovalDecision(result);
      setProcessResult((current) =>
        current?.pipeline_result
          ? {
              ...current,
              workflow_status: result.workflow_status,
              blocker_reason: result.blocker_reason,
              pipeline_result: {
                ...current.pipeline_result,
                approval_result: {
                  ...(current.pipeline_result.approval_result ?? { route: result.route }),
                  route: result.route,
                  approval_status: result.approval_status,
                  reason: result.reason
                },
                erp_export_ready: result.erp_export_ready,
                blocker_reason: result.blocker_reason
              }
            }
          : current
      );
      setVendorPreview(null);
      setStatus(result.workflow_status);
      await onWorkflowUpdated?.();
    } catch (error) {
      setStatus("failed");
      setError(error instanceof Error ? error.message : "Approval action failed because the API is unavailable.");
    } finally {
      setActiveAction(null);
    }
  }

  function mark(stage: string) {
    setTimestamps((current) => ({ ...current, [stage]: new Date().toISOString() }));
  }

  function ensureSignedIn() {
    if (!apiBaseUrl) {
      setError("NEXT_PUBLIC_API_BASE_URL is missing or invalid.");
      return false;
    }
    if (!isSignedIn) {
      setError("Sign in required. Use Demo login before upload, extraction, processing, or ERP export.");
      return false;
    }
    return true;
  }

  function getSignedInRequestContext() {
    if (!apiBaseUrl || !tenantId || !accessToken) return null;
    return { apiBaseUrl, tenantId, accessToken };
  }

  return (
    <div className="space-y-5">
      <section className="rounded-md border border-border bg-white">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <Play className="h-4 w-4 text-[hsl(var(--accent))]" />
            <h2 className="text-base font-semibold">Demo Walkthrough</h2>
          </div>
          <span className="text-xs text-muted">{status}</span>
        </div>
        <div className="divide-y divide-border">
          {demoSteps.map((step) => (
            <WalkthroughStep key={step.label} action={walkthroughAction(step.label)} step={step} />
          ))}
        </div>
      </section>

      <section className="scroll-mt-6 rounded-md border border-border bg-white" id="upload-invoice">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <UploadCloud className="h-4 w-4 text-[hsl(var(--accent))]" />
            <h2 className="text-base font-semibold">Invoice Upload</h2>
          </div>
          <span className="text-xs text-muted">{uploadResult ? "document stored" : "waiting for file"}</span>
        </div>
        <div className="space-y-4 p-4">
          <div className="rounded-md border border-border bg-[hsl(var(--background))] px-4 py-3 text-sm text-muted">
            Need a safe demo file? Download the generated{" "}
            <a className="font-medium text-foreground underline" href="/demo/fake-apflow-invoice.pdf">
              fake APFlow invoice
            </a>
            . It contains no real vendor, tax, bank, or customer data.
          </div>
          {signInRequired ? (
            <div className="flex items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              <span>Sign in required before uploading or processing invoices.</span>
              <button
                className="rounded-md border border-amber-300 bg-white px-3 py-2 text-sm disabled:text-muted"
                disabled={authStatus === "authenticating"}
                onClick={onDemoLogin}
                type="button"
              >
                Demo login
              </button>
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-[1fr_auto_auto_auto]">
            <label className="flex min-h-11 items-center gap-3 rounded-md border border-border px-3 py-2 text-sm">
              <FileText className="h-4 w-4 text-muted" />
              <span className="min-w-0 flex-1 truncate">{selectedFileName}</span>
              <input
                accept="application/pdf,image/png,image/jpeg"
                className="sr-only"
                key={resetSignal}
                type="file"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setError(null);
                }}
              />
            </label>
            <button
              className="rounded-md bg-black px-3 py-2 text-sm text-white disabled:bg-neutral-300"
              disabled={!file || signInRequired || isBusy}
              onClick={upload}
              type="button"
            >
              <UploadCloud className="mr-2 inline h-4 w-4" />
              {activeAction === "upload" ? "Uploading..." : "Upload"}
            </button>
            <button
              className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
              disabled={!documentId || signInRequired || isBusy}
              onClick={extractOnly}
              type="button"
            >
              <ScanText className="mr-2 inline h-4 w-4" />
              {activeAction === "extract" ? "Extracting..." : "Extract"}
            </button>
            <button
              className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
              disabled={!documentId || signInRequired || isBusy}
              onClick={processPipeline}
              type="button"
            >
              <Play className="mr-2 inline h-4 w-4" />
              {activeAction === "process" ? "Processing..." : "Process"}
            </button>
          </div>

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
          ) : null}
          {status === "uploading" || status === "extracting" || status === "processing" || status === "exporting" ? (
            <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">
              {status.charAt(0).toUpperCase() + status.slice(1)}. This may take a moment.
            </div>
          ) : null}

          {!uploadResult ? (
            <div className="rounded-md border border-border px-4 py-5 text-sm text-muted">
              No uploaded invoice document in this walkthrough yet.
            </div>
          ) : (
            <div className="grid gap-3 text-sm sm:grid-cols-4">
              <Metric label="Document" value={uploadResult.document.original_file_name} />
              <Metric label="Type" value={uploadResult.document.content_type} />
              <Metric label="Size" value={`${uploadResult.document.size_bytes} bytes`} />
              <Metric label="Storage" value={uploadResult.document.storage_provider} />
            </div>
          )}
        </div>
      </section>

      <section className="scroll-mt-6 rounded-md border border-border bg-white" id="workflow-timeline">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-base font-semibold">Workflow Timeline</h2>
        </div>
        <div className="p-4">
          <WorkflowTimeline stages={timelineStages} />
        </div>
      </section>

      <section className="scroll-mt-6 rounded-md border border-border bg-white" id="invoice-result">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-base font-semibold">Invoice Result Summary</h2>
        </div>
        <div className="space-y-4 p-4">
          {processResult ? (
            <>
              {processResult.workflow_status === "review_required" ? (
                <div className="space-y-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                  <p>Invoice requires human review before approval. Review required is a safe workflow outcome.</p>
                  <p>ERP export is disabled until review is corrected and invoice is approval-ready.</p>
                  {blockerReason ? <p>{blockerReason}</p> : null}
                </div>
              ) : null}
              <div className="grid gap-3 text-sm sm:grid-cols-3 xl:grid-cols-4">
                <Metric label="Invoice" value={invoice?.invoice_number ?? "pending review"} />
                <Metric label="Vendor" value={invoice?.supplier_name ?? "pending review"} />
                <Metric label="Total" value={invoice ? money(invoice.grand_total, invoice.currency) : "n/a"} />
                <Metric label="OCR provider" value={`${selectedOcrProvider} / ${selectedOcrStatus}`} />
                <Metric label="OCR confidence" value={confidence ? `${Math.round(confidence.average_confidence * 100)}%` : "n/a"} />
                <Metric label="OCR text length" value={parsedTextLength ? parsedTextLength.toString() : "0"} />
                <Metric label="Review" value={processResult.review_status.replaceAll("_", " ")} />
                <Metric label="Workflow" value={processResult.workflow_status.replaceAll("_", " ")} />
                <Metric label="PO match" value={pipeline?.po_match_result?.match_status.replaceAll("_", " ") ?? "n/a"} />
                <Metric label="Risk" value={pipeline?.fraud_risk_result?.risk_level ?? "n/a"} />
                <Metric label="Approval" value={approvalDisplayStatus?.replaceAll("_", " ") ?? "n/a"} />
                <Metric label="ERP ready" value={erpExportReady ? "yes" : "no"} />
                <Metric label="Review fields" value={reviewRequiredFields.length ? reviewRequiredFields.join(", ") : "none"} />
                <Metric label="Invoice created" value={invoiceCreated ? "yes" : "no"} />
              </div>
              {approvalNeedsAction ? (
                <div className="rounded-md border border-border px-4 py-4 text-sm">
                  <p className="font-medium">AP review action required</p>
                  <p className="mt-1 text-xs text-muted">Approval actions apply to the current processed invoice.</p>
                  <p className="mt-1 text-muted">
                    {pipeline?.approval_result?.reason ?? blockerReason ?? "Approval policy blocked this invoice."}
                  </p>
                  {canApproveInvoice ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
                        disabled={isBusy}
                        onClick={() => decideApproval("approve")}
                        type="button"
                      >
                        Approve
                      </button>
                      <button
                        className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
                        disabled={isBusy}
                        onClick={() => decideApproval("reject")}
                        type="button"
                      >
                        Reject
                      </button>
                      <button
                        className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
                        disabled={isBusy}
                        onClick={() => decideApproval("hold")}
                        type="button"
                      >
                        Keep on Hold
                      </button>
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-muted">Your current role cannot resolve blocked invoices.</p>
                  )}
                  {approvalDecision ? (
                    <p className="mt-3 text-xs text-muted">
                      Latest decision: {approvalDecision.approval_status.replaceAll("_", " ")}. {approvalDecision.reason}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {blockedWithoutCurrentInvoice ? (
                <div className="rounded-md border border-border px-4 py-4 text-sm text-muted">
                  Approval actions require a current processed invoice record.
                </div>
              ) : null}
            </>
          ) : (
            <div className="rounded-md border border-border px-4 py-5 text-sm text-muted">
              Process an uploaded invoice to populate the summary.
            </div>
          )}
        </div>
      </section>

      <section className="scroll-mt-6 rounded-md border border-border bg-white" id="ocr-review">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-base font-semibold">OCR Review</h2>
        </div>
        <div className="space-y-4 p-4">
          {confidence ? (
            <div className="grid gap-3 text-sm sm:grid-cols-4">
              <Metric label="Average confidence" value={`${Math.round(confidence.average_confidence * 100)}%`} />
              <Metric label="Low confidence fields" value={confidence.low_confidence_fields.toString()} />
              <Metric label="Review status" value={(reviewStatus ?? "pending").replaceAll("_", " ")} />
              <Metric label="Review tasks" value={reviewTasks.length.toString()} />
              <Metric label="Parsed text length" value={parsedTextLength.toString()} />
              <Metric label="Parsed results" value={parsedResultCount.toString()} />
              <Metric label="OCR exit code" value={String(ocrRawResponse?.ocr_exit_code ?? ocrProviderMetadata?.ocr_exit_code ?? "n/a")} />
              <Metric label="Content type" value={ocrRawResponse?.detected_content_type ?? ocrProviderMetadata?.detected_content_type ?? "n/a"} />
              <Metric label="Sent file" value={sentFileName} />
              <Metric label="Sent filetype" value={sentFiletype} />
              <Metric label="Sent content type" value={sentContentType} />
            </div>
          ) : null}
          {reviewRequiredFields.length ? (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Review required: {reviewRequiredFields.join(", ")}
            </div>
          ) : null}
          {ocrResult?.error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              OCR provider error: {ocrResult.error}
            </div>
          ) : null}
          {fileTypeAdvice ? (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {fileTypeAdvice}
            </div>
          ) : null}
          {fields.length ? (
            <div className="divide-y divide-border rounded-md border border-border">
              <div className="grid gap-3 bg-[hsl(var(--background))] px-3 py-2 text-xs font-medium text-muted sm:grid-cols-[170px_1fr_100px_120px]">
                <span>Field</span>
                <span>Value</span>
                <span>Confidence</span>
                <span>Review</span>
              </div>
              {fields.map((field) => (
                <div
                  className="grid gap-3 px-3 py-2 text-sm sm:grid-cols-[170px_1fr_100px_120px]"
                  key={field.field_name}
                >
                  <span className="font-medium">{field.field_name.replaceAll("_", " ")}</span>
                  <span className="truncate text-muted" title={String(field.value ?? "missing")}>
                    {field.value ?? "missing"}
                  </span>
                  <span>{Math.round(field.confidence * 100)}%</span>
                  <span className={field.requires_review ? "text-amber-700" : "text-green-700"}>
                    {field.requires_review ? "yes" : "no"}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-md border border-border px-4 py-5 text-sm text-muted">
              {extractResult || processResult
                ? parsedTextLength > 0
                  ? "OCR text was received but invoice fields could not be confidently parsed."
                  : "OCR provider returned no parsed text."
                : "Run extraction to view field confidence."}
            </div>
          )}
          {ocrTextPreview ? (
            <details className="rounded-md border border-border">
              <summary className="cursor-pointer px-3 py-2 text-sm font-medium">OCR text preview</summary>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t border-border p-3 text-xs text-muted">
                {ocrTextPreview}
              </pre>
            </details>
          ) : null}
          {reviewTasks.length ? (
            <div className="space-y-3 rounded-md border border-border p-3">
              <div>
                <h3 className="text-sm font-semibold">Human review corrections</h3>
                <p className="mt-1 text-xs text-muted">
                  Save corrected fields, then click Process to continue with the corrected extraction.
                </p>
              </div>
              {visibleReviewIssues.length ? (
                <div className="space-y-1 text-sm text-amber-800">
                  {visibleReviewIssues.map((issue) => (
                    <p key={`${issue.field_name}-${issue.message}`}>
                      {issue.field_name.replaceAll("_", " ")}: {issue.message}
                    </p>
                  ))}
                </div>
              ) : null}
              {correctedIssueFields.size ? (
                <p className="text-sm text-muted">
                  Saved corrections are pending re-check on the next Process run.
                </p>
              ) : null}
              {!visibleReviewIssues.length && resolvedReviewFields.length ? (
                <p className="text-sm text-green-700">
                  Resolved fields: {resolvedReviewFields.join(", ")}.
                </p>
              ) : null}
              {correctionFields.length ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {correctionFields.map((fieldName) => (
                    <label className="text-sm" key={fieldName}>
                      <span className="mb-1 block text-xs text-muted">{fieldName.replaceAll("_", " ")}</span>
                      <input
                        className="w-full rounded-md border border-border px-3 py-2"
                        onChange={(event) =>
                          setCorrections((current) => ({ ...current, [fieldName]: event.target.value }))
                        }
                        placeholder={`Correct ${fieldName.replaceAll("_", " ")}`}
                        type="text"
                        value={corrections[fieldName] ?? ""}
                      />
                    </label>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted">No missing required fields are waiting for correction.</p>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <button
                  className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
                  disabled={!canCorrectReview || !correctionFields.length || signInRequired || isBusy}
                  onClick={submitCorrections}
                  type="button"
                >
                  Submit corrections
                </button>
                <span className="text-xs text-muted">
                  {canCorrectReview ? correctionMessage ?? "Correction endpoint is available." : "Your role cannot submit corrections."}
                </span>
              </div>
            </div>
          ) : null}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="scroll-mt-6 rounded-md border border-border bg-white" id="erp-export">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-base font-semibold">Mock ERP Export</h2>
            <button
              className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
              disabled={signInRequired || !canExportErp || !erpExportReady || !invoiceId || Boolean(erpResult) || isBusy}
              onClick={exportToMockErp}
              type="button"
            >
              <Send className="mr-2 inline h-4 w-4" />
              {activeAction === "export" ? "Exporting..." : "Export to Mock ERP"}
            </button>
          </div>
          <div className="space-y-4 p-4 text-sm">
            {invoiceId ? (
              <p className="text-xs text-muted">Using current processed invoice {invoice?.invoice_number ?? invoiceId}.</p>
            ) : null}
            {erpResult ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <Metric label="Sync" value={erpResult.status} />
                <Metric label="Adapter" value={erpResult.adapter_type} />
                <Metric label="External ID" value={erpResult.external_id ?? "not returned"} />
              </div>
            ) : (
              <div className="rounded-md border border-border px-4 py-5 text-muted">
                {signInRequired
                  ? "Sign in before exporting invoices to ERP."
                  : !canExportErp
                  ? "Your current role cannot export invoices to ERP."
                  : erpExportReady
                    ? "Invoice is ready for explicit mock ERP export."
                    : exportReadinessBlocker(pipeline, reviewStatus, blockerReason)}
              </div>
            )}
            {erpLogs.length ? (
              <div className="divide-y divide-border rounded-md border border-border">
                {erpLogs.map((log) => (
                  <div className="grid gap-3 px-3 py-2 sm:grid-cols-[120px_1fr_140px]" key={log.sync_id}>
                    <span className="font-medium">{log.status}</span>
                    <span>{log.operation.replaceAll("_", " ")}</span>
                    <span className="text-muted">{log.external_id ?? "no external id"}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <div className="scroll-mt-6 rounded-md border border-border bg-white" id="vendor-portal-preview">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-base font-semibold">Vendor-Safe Status Preview</h2>
            <button
              className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
              disabled={signInRequired || !invoiceId || isBusy}
              onClick={loadVendorPreview}
              type="button"
            >
              <ExternalLink className="mr-2 inline h-4 w-4" />
              {activeAction === "vendor-preview" ? "Loading..." : "Preview"}
            </button>
          </div>
          <div className="p-4 text-sm">
            {invoiceId ? (
              <p className="mb-3 text-xs text-muted">
                Previewing the current processed invoice {invoice?.invoice_number ?? invoiceId}.
              </p>
            ) : null}
            {vendorPreview ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Metric label="Invoice" value={vendorPreview.invoice_number} />
                <Metric label="Vendor status" value={vendorPreview.status.replaceAll("_", " ")} />
                <Metric label="Payment" value={vendorPreview.payment_status ?? "not scheduled"} />
                <Metric label="Visible total" value={money(vendorPreview.grand_total, vendorPreview.currency)} />
                <div className="rounded-md border border-border px-3 py-2 sm:col-span-2">
                  <p className="text-xs text-muted">Public message</p>
                  <p className="mt-1">{vendorPreview.public_message}</p>
                </div>
              </div>
            ) : (
              <div className="rounded-md border border-border px-4 py-5 text-muted">
                {signInRequired
                  ? "Sign in before preparing a vendor-safe preview."
                  : invoiceId
                    ? "Vendor-safe preview is available for this processed invoice."
                    : blockerReason
                      ? blockerReason
                      : pipeline
                        ? "This process result did not create an invoice record to preview."
                      : "Process an invoice, then preview the restricted vendor view."}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function buildDemoSteps(input: {
  signedIn: boolean;
  file: File | null;
  uploadResult: UploadResult | null;
  extractResult: ExtractResult | null;
  processResult: ProcessResult | null;
  erpResult: ERPSyncResult | null;
  vendorPreview: VendorInvoiceStatus | null;
  status: string;
  error: string | null;
  erpExportReady: boolean;
}): Array<{ label: string; status: StepStatus; description: string }> {
  const failed = input.status === "failed";
  return [
    {
      label: "Step 1",
      status: input.signedIn ? "completed" : "active",
      description: input.signedIn ? "Demo tenant session is signed in." : "Click Demo login to start a tenant session."
    },
    {
      label: "Step 2",
      status: statusFor(Boolean(input.uploadResult), input.file ? "active" : "pending", failed && !input.uploadResult),
      description: "Upload an invoice PDF or image into tenant-scoped storage."
    },
    {
      label: "Step 3",
      status: statusFor(Boolean(input.extractResult || input.processResult), input.uploadResult ? "active" : "pending", failed),
      description: "Run OCR and inspect confidence before processing."
    },
    {
      label: "Step 4",
      status: statusFor(Boolean(input.processResult), input.extractResult || input.uploadResult ? "active" : "pending", failed),
      description: "Continue through validation, duplicate check, PO match, risk, and approval."
    },
    {
      label: "Step 5",
      status: input.processResult ? "completed" : "pending",
      description: input.processResult
        ? `Workflow is ${input.processResult.workflow_status.replaceAll("_", " ")}.`
        : "Review the workflow result after processing."
    },
    {
      label: "Step 6",
      status: input.erpResult ? "completed" : input.erpExportReady ? "active" : "pending",
      description: input.erpResult
        ? `Exported to ${input.erpResult.external_id ?? "mock ERP"}.`
        : "Export approval-ready invoices to the mock Priority adapter."
    },
    {
      label: "Step 7",
      status: input.vendorPreview ? "completed" : input.processResult ? "active" : "pending",
      description: input.vendorPreview
        ? `Vendor sees ${input.vendorPreview.status.replaceAll("_", " ")}.`
        : "Preview the vendor-safe status without internal risk details."
    }
  ];
}

function WalkthroughStep({
  step,
  action
}: {
  step: { label: string; status: StepStatus; description: string };
  action: { label: string; action: () => void; disabled: boolean } | null;
}) {
  return (
    <div className="grid gap-3 px-4 py-3 text-sm md:grid-cols-[170px_1fr_auto]">
      <div className="flex items-center gap-2">
        {step.status === "completed" ? (
          <CheckCircle2 className="h-4 w-4 text-green-700" />
        ) : step.status === "failed" ? (
          <AlertTriangle className="h-4 w-4 text-red-700" />
        ) : (
          <span className="h-2.5 w-2.5 rounded-full bg-border" />
        )}
        <span className="font-medium">{step.label}</span>
      </div>
      <span className="text-muted">{step.description}</span>
      {action ? (
        <button
          className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
          disabled={action.disabled}
          onClick={action.action}
          type="button"
        >
          {action.label}
        </button>
      ) : (
        <span className="text-xs text-muted">{step.status}</span>
      )}
    </div>
  );
}

function buildTimeline(input: {
  uploadResult: UploadResult | null;
  extractResult: ExtractResult | null;
  processResult: ProcessResult | null;
  erpResult: ERPSyncResult | null;
  timestamps: Record<string, string>;
}): TimelineStage[] {
  const pipeline = input.processResult?.pipeline_result;
  const reviewStatus = input.processResult?.review_status ?? input.extractResult?.review_status;
  const processed = Boolean(input.processResult);
  const reviewRequired = reviewStatus === "review_required";
  const poStatus = pipeline?.po_match_result?.match_status;
  const riskLevel = pipeline?.fraud_risk_result?.risk_level;
  const validationStatus = pipeline?.validation_result?.validation_status;
  const duplicateStatus = pipeline?.duplicate_result?.status;
  const approvalRoute = pipeline?.approval_result?.route;
  const approvalStatus = pipeline?.approval_result?.approval_status;
  const exportBlocker = exportReadinessBlocker(
    pipeline,
    reviewStatus,
    input.processResult?.blocker_reason ?? pipeline?.blocker_reason
  );

  return [
    {
      id: "uploaded",
      label: "Uploaded",
      status: input.uploadResult ? "completed" : "pending",
      timestamp: input.timestamps.uploaded,
      summary: input.uploadResult
        ? `${input.uploadResult.document.original_file_name} stored in ${input.uploadResult.document.storage_provider}.`
        : "Waiting for invoice upload."
    },
    {
      id: "extracted",
      label: "Extracted",
      status: input.extractResult || input.processResult ? "completed" : input.uploadResult ? "active" : "pending",
      timestamp: input.timestamps.extracted ?? input.timestamps.processed,
      summary: input.extractResult || input.processResult ? "OCR fields and confidence are available." : "OCR has not run yet."
    },
    {
      id: "review",
      label: reviewRequired ? "Review Required" : "Review Not Required",
      status: reviewStatus ? (reviewRequired ? "warning" : "completed") : "pending",
      timestamp: input.timestamps.extracted ?? input.timestamps.processed,
      summary: reviewStatus ? `Human review status is ${reviewStatus.replaceAll("_", " ")}.` : "Review status pending.",
      warning: reviewRequired ? "Required fields need human review before approval." : undefined
    },
    {
      id: "validated",
      label: "Validated",
      status: validationStatus ? (validationStatus === "failed" ? "warning" : "completed") : "pending",
      timestamp: input.timestamps.processed,
      summary: validationStatus
        ? `Validation ${validationStatus}.`
        : "Validation waits for processing."
    },
    {
      id: "duplicate_checked",
      label: "Duplicate Checked",
      status: duplicateStatus ? (duplicateStatus === "likely_duplicate" ? "warning" : "completed") : "pending",
      timestamp: input.timestamps.processed,
      summary: duplicateStatus
        ? `Duplicate status ${duplicateStatus.replaceAll("_", " ")}.`
        : "Duplicate check waits for processing."
    },
    {
      id: "po_matched",
      label: "PO Matched",
      status: poStatus ? (poStatus === "matched" ? "completed" : "warning") : "pending",
      timestamp: input.timestamps.processed,
      summary: poStatus ? `PO match is ${poStatus.replaceAll("_", " ")}.` : "PO matching waits for processing.",
      warning: poStatus && poStatus !== "matched" ? "AP review may be required." : undefined
    },
    {
      id: "risk_scored",
      label: "Risk Scored",
      status: riskLevel ? (["high", "critical"].includes(riskLevel) ? "warning" : "completed") : "pending",
      timestamp: input.timestamps.processed,
      summary: riskLevel ? `Risk level is ${riskLevel}.` : "Risk scoring waits for processing.",
      warning: riskLevel && ["high", "critical"].includes(riskLevel) ? "Review risk evidence before payment." : undefined
    },
    {
      id: "approval_routed",
      label: approvalStatus && ["approved", "rejected", "on_hold"].includes(approvalStatus)
        ? "Approval Resolved"
        : "Approval Routed",
      status: approvalStatus === "approved"
        ? "completed"
        : approvalStatus && ["rejected", "on_hold", "blocked"].includes(approvalStatus)
          ? "warning"
          : approvalRoute
            ? "completed"
            : "pending",
      timestamp: input.timestamps.processed,
      summary: approvalStatus
        ? `Approval status is ${approvalStatus.replaceAll("_", " ")}.`
        : approvalRoute
          ? `Approval route is ${approvalRoute.replaceAll("_", " ")}.`
        : "Approval route waits for processing."
    },
    {
      id: "erp_export_ready",
      label: "ERP Export Ready",
      status: pipeline?.erp_export_ready ? "completed" : processed ? "warning" : "pending",
      timestamp: input.timestamps.processed,
      summary: pipeline?.erp_export_ready ? "Invoice can be exported explicitly." : exportBlocker
    },
    {
      id: "exported_to_erp",
      label: "Exported To ERP",
      status: input.erpResult ? "completed" : "pending",
      timestamp: input.timestamps.exported_to_erp,
      summary: input.erpResult
        ? `Mock ERP export ${input.erpResult.status}; external ID ${input.erpResult.external_id ?? "not returned"}.`
        : "No ERP export has been triggered."
    }
  ];
}

function exportReadinessBlocker(
  pipeline: ProcessResult["pipeline_result"] | undefined,
  reviewStatus: string | undefined,
  blockerReason?: string | null
) {
  if (blockerReason) return blockerReason;
  if (reviewStatus === "review_required") return "Human review must be resolved before ERP export.";
  if (!pipeline) return "Process an invoice to determine export readiness.";
  if (pipeline.approval_result?.route === "blocked") return "Approval policy blocked this invoice.";
  if (pipeline.approval_result?.route) return `Approval route ${pipeline.approval_result.route.replaceAll("_", " ")} is not export-ready.`;
  if (pipeline.po_match_result?.match_status) {
    return `PO match result is ${pipeline.po_match_result.match_status.replaceAll("_", " ")}.`;
  }
  return "Invoice is not ready for export yet.";
}

function statusFor(done: boolean, waiting: StepStatus, failed: boolean): StepStatus {
  if (done) return "completed";
  if (failed) return "failed";
  return waiting;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border px-3 py-2">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 truncate font-medium">{value}</p>
    </div>
  );
}

function mergeCorrectedFields(fields: ExtractedField[], correctedFields: Record<string, string | number>) {
  const merged = new Map(fields.map((field) => [field.field_name, field]));
  for (const [fieldName, value] of Object.entries(correctedFields)) {
    merged.set(fieldName, {
      field_name: fieldName,
      value,
      confidence: 1,
      raw_text: "manual correction",
      requires_review: false
    });
  }
  return Array.from(merged.values());
}

function buildCorrectionDefaults(
  correctionFields: string[],
  fields: ExtractedField[],
  issues: ReviewIssue[],
  tasks: ReviewTask[]
) {
  const defaults: Record<string, string> = {};
  const fieldMap = new Map(fields.map((field) => [field.field_name, field]));
  const issueMap = new Map(issues.map((issue) => [issue.field_name, issue]));
  const correctedFields = Object.assign({}, ...tasks.map((task) => task.corrected_fields ?? {})) as Record<
    string,
    string | number
  >;

  for (const fieldName of correctionFields) {
    const correctedValue = correctedFields[fieldName];
    const fieldValue = fieldMap.get(fieldName)?.value;
    const issueValue = issueMap.get(fieldName)?.current_value;
    const value = correctedValue ?? fieldValue ?? issueValue;
    if (value !== undefined && value !== null && value !== "") {
      defaults[fieldName] = formatCorrectionValue(fieldName, value);
    }
  }
  return defaults;
}

function shouldShowApprovalDecisionActions(input: {
  invoiceCreated: boolean;
  invoiceId: string | undefined;
  workflowStatus: string | undefined;
  approvalRoute: string | undefined;
  approvalStatus: string | undefined;
}) {
  return Boolean(
    input.invoiceCreated &&
      input.invoiceId &&
      isBlockedApprovalState(input) &&
      !["approved", "rejected", "on_hold"].includes(input.approvalStatus ?? "")
  );
}

function isBlockedApprovalState(input: {
  workflowStatus: string | undefined;
  approvalRoute: string | undefined;
  approvalStatus: string | undefined;
}) {
  return (
    input.workflowStatus === "blocked" ||
    input.approvalRoute === "blocked" ||
    input.approvalStatus === "blocked"
  );
}

function stringifyCorrections(correctedFields: Record<string, string | number>) {
  return Object.fromEntries(
    Object.entries(correctedFields).map(([fieldName, value]) => [fieldName, formatCorrectionValue(fieldName, value)])
  );
}

function formatCorrectionValue(fieldName: string, value: string | number) {
  if (typeof value === "number" && ["subtotal", "tax_total", "grand_total"].includes(fieldName)) {
    return value.toFixed(2);
  }
  return String(value);
}

function money(value: number, currency: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 2
  }).format(value || 0);
}
