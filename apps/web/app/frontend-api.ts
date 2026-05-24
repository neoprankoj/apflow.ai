"use client";

export type AuthStatus = "unauthenticated" | "authenticating" | "authenticated" | "failed";

const TOKEN_STORAGE_KEY = "apflow.accessToken";

export class ApiRequestError extends Error {
  status?: number;
  detail?: string;

  constructor(message: string, status?: number, detail?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
  }
}

export type PriorityMapping = {
  version?: string;
  vendors?: PriorityEntityMapping | null;
  purchase_orders?: PriorityEntityMapping | null;
  invoice_export?: PriorityEntityMapping | null;
  updated_at?: string | null;
};

export type PriorityEntityMapping = {
  entity_name: string;
  external_id_field: string;
  fields: Record<string, string>;
  line_items_entity_name?: string | null;
  line_item_fields?: Record<string, string> | null;
  enabled?: boolean;
};

export type PriorityMappingResponse = {
  tenant_id: string;
  mapping: PriorityMapping | null;
};

export type PriorityMappingValidationResult = {
  status: string;
  errors: string[];
  warnings: string[];
  summary: Record<string, unknown>;
};

export type PriorityReadinessCheck = {
  key: string;
  label: string;
  status: "ok" | "missing" | "disabled" | "warning" | "not_applicable" | string;
  message: string;
  safe_detail?: string | null;
};

export type PriorityReadinessResponse = {
  status: "ready" | "not_ready" | "partially_ready" | string;
  mode: string;
  read_only_fetch_enabled: boolean;
  writes_enabled: boolean;
  base_url_configured: boolean;
  company_configured: boolean;
  environment_configured: boolean;
  auth_configured: boolean;
  service_root_checked: boolean;
  metadata_checked: boolean;
  service_root_available?: boolean | null;
  metadata_available?: boolean | null;
  checks: PriorityReadinessCheck[];
  warnings: string[];
  errors: string[];
  message: string;
};

export type PrioritySyncPreviewKind = "vendors" | "purchase_orders";
export type PrioritySyncPreviewSource = "sample" | "priority";

export type PrioritySyncPreviewResponse = {
  status: string;
  kind: PrioritySyncPreviewKind;
  mode: string;
  source: string;
  mapping_status: string;
  records_previewed: number;
  raw_records: Record<string, unknown>[];
  mapped_records: Record<string, unknown>[];
  errors: string[];
  warnings: string[];
  message: string;
};

export type PriorityImportPlanItem = {
  action: "would_create" | "would_update" | "would_skip" | "would_conflict" | string;
  reason: string;
  mapped_record: Record<string, unknown>;
  matched_existing_id?: string | null;
  diff?: Record<string, unknown> | null;
  warnings: string[];
};

export type PriorityImportPlanResponse = {
  status: string;
  kind: PrioritySyncPreviewKind;
  mode: string;
  source: string;
  records_planned: number;
  summary: Record<string, number>;
  items: PriorityImportPlanItem[];
  warnings: string[];
  errors: string[];
  message: string;
};

export type PriorityImportResultItem = {
  external_id?: string | null;
  action_requested: string;
  result: "created" | "updated" | "skipped" | "conflict" | "blocked" | "failed" | string;
  apflow_record_id?: string | null;
  reason: string;
  warnings: string[];
};

export type PriorityImportResult = {
  status: string;
  kind: PrioritySyncPreviewKind;
  summary: Record<string, number>;
  items: PriorityImportResultItem[];
  warnings: string[];
  errors: string[];
  message: string;
};

export type PriorityImportedVendorRecord = {
  apflow_vendor_id: string;
  external_id?: string | null;
  name: string;
  tax_id?: string | null;
  email?: string | null;
  payment_terms?: string | null;
  source_adapter: string;
  imported_from_priority: boolean;
  last_imported_at?: string | null;
  last_import_action?: string | null;
  external_reference_id?: string | null;
};

export type PriorityImportedPurchaseOrderRecord = {
  apflow_purchase_order_id: string;
  po_number: string;
  external_id?: string | null;
  vendor_id?: string | null;
  vendor_external_id?: string | null;
  status: string;
  total_amount: number;
  currency: string;
  source_adapter: string;
  imported_from_priority: boolean;
  last_imported_at?: string | null;
  last_import_action?: string | null;
  external_reference_id?: string | null;
};

export type PriorityImportedRecordsResponse<TRecord> = {
  tenant_id: string;
  kind: PrioritySyncPreviewKind;
  records: TRecord[];
};

export type ProductReadinessCheck = {
  key: string;
  label: string;
  status: "pass" | "fail" | "warning" | "not_applicable" | string;
  category: string;
  message: string;
  next_step?: string | null;
  safe_detail?: string | null;
};

export type ProductReadinessLevel = {
  key: string;
  status: "ready" | "not_ready" | "partially_ready" | string;
  summary: string;
  blockers: string[];
  warnings: string[];
};

export type ProductReadinessResponse = {
  environment: string;
  generated_at: string;
  demo_ready: ProductReadinessLevel;
  pilot_ready: ProductReadinessLevel;
  production_ready: ProductReadinessLevel;
  checks: ProductReadinessCheck[];
  message: string;
};

export type PaymentStatusRead = {
  id: string;
  tenant_id: string;
  invoice_id: string;
  status: string;
  source: string;
  amount_due?: number | null;
  amount_paid?: number | null;
  currency: string;
  scheduled_payment_date?: string | null;
  paid_at?: string | null;
  external_payment_reference?: string | null;
  safe_vendor_message?: string | null;
  last_synced_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type PaymentStatusSummary = {
  tenant_id: string;
  totals_by_status: Record<string, number>;
  pending_count: number;
  scheduled_count: number;
  paid_count: number;
  failed_or_disputed_count: number;
  latest_updates: PaymentStatusRead[];
};

export type PaymentStatusUpdate = {
  status?: string;
  amount_paid?: number | null;
  scheduled_payment_date?: string | null;
  paid_at?: string | null;
  safe_vendor_message?: string | null;
  internal_note?: string | null;
  external_payment_reference?: string | null;
};

export type VendorAccessRead = {
  id: string;
  tenant_id: string;
  vendor_id: string;
  vendor_name?: string | null;
  email: string;
  label?: string | null;
  status: string;
  expires_at?: string | null;
  revoked_at?: string | null;
  revoked_by_user_id?: string | null;
  created_by_user_id?: string | null;
  rotated_from_access_id?: string | null;
  last_used_at?: string | null;
  token_prefix?: string | null;
  created_at: string;
  updated_at?: string | null;
};

export type VendorAccessCreatedResponse = VendorAccessRead & {
  access_token: string;
  access_url?: string | null;
  message: string;
};

export type VendorAccessRotateResponse = {
  old_access: VendorAccessRead;
  new_access: VendorAccessRead;
  access_token: string;
  access_url?: string | null;
  message: string;
};

export type VendorAccessRevokeResponse = {
  id: string;
  status: string;
  revoked_at?: string | null;
  message: string;
};

export type VendorAccessCreatePayload = {
  tenant_id: string;
  email: string;
  vendor_id?: string | null;
  vendor_name?: string | null;
  supplier_name?: string | null;
  label?: string | null;
  ttl_days?: number | null;
  expires_at?: string | null;
};

export function getApiBaseUrl() {
  const value = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

export function getStoredToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearStoredToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export async function apiFetch<T>(
  apiBaseUrl: string,
  path: string,
  options: RequestInit & { token?: string | null; action?: string } = {}
): Promise<T> {
  const { token, action = "Request", headers, body, ...init } = options;
  const requestHeaders = new Headers(headers);
  if (token) {
    requestHeaders.set("Authorization", `Bearer ${token}`);
  }
  if (body !== undefined && !(body instanceof FormData) && !requestHeaders.has("content-type")) {
    requestHeaders.set("content-type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      body,
      headers: requestHeaders,
      cache: init.cache ?? "no-store"
    });
  } catch (error) {
    logApiError(action, error);
    throw new ApiRequestError(`${action} failed (${path}): API unavailable: failed to fetch`);
  }

  if (!response.ok) {
    const detail = await readResponseDetail(response);
    const message = `${action} failed (${path}): ${response.status} ${detail}`;
    logApiError(action, { status: response.status, detail });
    throw new ApiRequestError(message, response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getPriorityMapping(apiBaseUrl: string, token: string, tenantId: string) {
  return apiFetch<PriorityMappingResponse>(
    apiBaseUrl,
    `/erp/priority/mapping?tenant_id=${encodeURIComponent(tenantId)}`,
    { token, action: "Load Priority mapping" }
  );
}

export function validatePriorityMapping(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  mapping: PriorityMapping
) {
  return apiFetch<PriorityMappingValidationResult>(apiBaseUrl, "/erp/priority/validate-mapping", {
    method: "POST",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, mapping }),
    action: "Validate Priority mapping"
  });
}

export function savePriorityMapping(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  mapping: PriorityMapping
) {
  return apiFetch<Record<string, unknown>>(apiBaseUrl, "/erp/priority/mapping", {
    method: "PUT",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, mapping }),
    action: "Save Priority mapping"
  });
}

export function getPriorityReadiness(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  checkRemote = false
) {
  const params = new URLSearchParams({ tenant_id: tenantId });
  if (checkRemote) params.set("check_remote", "true");
  return apiFetch<PriorityReadinessResponse>(apiBaseUrl, `/erp/priority/readiness?${params.toString()}`, {
    token,
    action: checkRemote ? "Run Priority connection drill" : "Load Priority readiness"
  });
}

export function previewPrioritySync(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  kind: PrioritySyncPreviewKind,
  source: PrioritySyncPreviewSource = "sample",
  limit = 10
) {
  return apiFetch<PrioritySyncPreviewResponse>(apiBaseUrl, "/erp/priority/sync-preview", {
    method: "POST",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, kind, source, limit }),
    action: kind === "vendors" ? "Preview Priority vendor sync" : "Preview Priority purchase order sync"
  });
}

export function previewPriorityVendorSync(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  source: PrioritySyncPreviewSource = "sample"
) {
  return previewPrioritySync(apiBaseUrl, token, tenantId, "vendors", source);
}

export function previewPriorityPurchaseOrderSync(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  source: PrioritySyncPreviewSource = "sample"
) {
  return previewPrioritySync(apiBaseUrl, token, tenantId, "purchase_orders", source);
}

export function generatePriorityImportPlan(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  kind: PrioritySyncPreviewKind,
  source: PrioritySyncPreviewSource = "sample",
  limit = 10
) {
  return apiFetch<PriorityImportPlanResponse>(apiBaseUrl, "/erp/priority/import-plan", {
    method: "POST",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, kind, source, limit }),
    action: kind === "vendors" ? "Generate Priority vendor import plan" : "Generate Priority purchase order import plan"
  });
}

export function generatePriorityVendorImportPlan(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  source: PrioritySyncPreviewSource = "sample"
) {
  return generatePriorityImportPlan(apiBaseUrl, token, tenantId, "vendors", source);
}

export function generatePriorityPurchaseOrderImportPlan(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  source: PrioritySyncPreviewSource = "sample"
) {
  return generatePriorityImportPlan(apiBaseUrl, token, tenantId, "purchase_orders", source);
}

export function importPriorityRecords(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  kind: PrioritySyncPreviewKind,
  source: PrioritySyncPreviewSource,
  selectedExternalIds: string[],
  confirmation: string,
  allowCreates: boolean,
  allowUpdates: boolean
) {
  return apiFetch<PriorityImportResult>(apiBaseUrl, "/erp/priority/import", {
    method: "POST",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      tenant_id: tenantId,
      kind,
      source,
      selected_external_ids: selectedExternalIds,
      confirmation,
      allow_creates: allowCreates,
      allow_updates: allowUpdates
    }),
    action: kind === "vendors" ? "Import selected Priority vendors" : "Import selected Priority purchase orders"
  });
}

export function getPriorityImportedVendors(apiBaseUrl: string, token: string, tenantId: string) {
  return apiFetch<PriorityImportedRecordsResponse<PriorityImportedVendorRecord>>(
    apiBaseUrl,
    `/erp/priority/imported/vendors?tenant_id=${encodeURIComponent(tenantId)}`,
    { token, action: "Load imported Priority vendors" }
  );
}

export function getPriorityImportedPurchaseOrders(apiBaseUrl: string, token: string, tenantId: string) {
  return apiFetch<PriorityImportedRecordsResponse<PriorityImportedPurchaseOrderRecord>>(
    apiBaseUrl,
    `/erp/priority/imported/purchase-orders?tenant_id=${encodeURIComponent(tenantId)}`,
    { token, action: "Load imported Priority purchase orders" }
  );
}

export function getProductReadiness(apiBaseUrl: string, token: string) {
  return apiFetch<ProductReadinessResponse>(apiBaseUrl, "/ready/product", {
    token,
    action: "Load product readiness"
  });
}

export function listPaymentStatuses(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  filters: { invoiceId?: string; status?: string } = {}
) {
  const params = new URLSearchParams({ tenant_id: tenantId });
  if (filters.invoiceId) params.set("invoice_id", filters.invoiceId);
  if (filters.status) params.set("status", filters.status);
  return apiFetch<PaymentStatusRead[]>(apiBaseUrl, `/payments/statuses?${params.toString()}`, {
    token,
    action: "Load payment statuses"
  });
}

export function getPaymentSummary(apiBaseUrl: string, token: string, tenantId: string) {
  return apiFetch<PaymentStatusSummary>(
    apiBaseUrl,
    `/payments/summary?tenant_id=${encodeURIComponent(tenantId)}`,
    { token, action: "Load payment summary" }
  );
}

export function updatePaymentStatus(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  paymentStatusId: string,
  payload: PaymentStatusUpdate
) {
  return apiFetch<PaymentStatusRead>(
    apiBaseUrl,
    `/payments/statuses/${encodeURIComponent(paymentStatusId)}?tenant_id=${encodeURIComponent(tenantId)}`,
    {
      method: "PATCH",
      token,
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      action: "Update payment status"
    }
  );
}

export function runMockPaymentSync(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  invoiceId?: string
) {
  return apiFetch<PaymentStatusRead[]>(apiBaseUrl, "/payments/sync/mock", {
    method: "POST",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, mode: "mock", invoice_id: invoiceId ?? null }),
    action: "Run mock payment sync"
  });
}

export function listVendorAccesses(apiBaseUrl: string, token: string, tenantId: string) {
  return apiFetch<VendorAccessRead[]>(
    apiBaseUrl,
    `/vendor/accesses?tenant_id=${encodeURIComponent(tenantId)}`,
    { token, action: "Load vendor access records" }
  );
}

export function createVendorAccess(
  apiBaseUrl: string,
  token: string,
  payload: VendorAccessCreatePayload
) {
  return apiFetch<VendorAccessCreatedResponse>(apiBaseUrl, "/vendor/accesses", {
    method: "POST",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    action: "Create vendor access"
  });
}

export function revokeVendorAccess(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  accessId: string
) {
  return apiFetch<VendorAccessRevokeResponse>(
    apiBaseUrl,
    `/vendor/accesses/${encodeURIComponent(accessId)}/revoke?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "POST", token, action: "Revoke vendor access" }
  );
}

export function rotateVendorAccess(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  accessId: string
) {
  return apiFetch<VendorAccessRotateResponse>(
    apiBaseUrl,
    `/vendor/accesses/${encodeURIComponent(accessId)}/rotate?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "POST", token, action: "Rotate vendor access" }
  );
}

async function readResponseDetail(response: Response) {
  try {
    const body = (await response.json()) as { detail?: unknown; message?: unknown };
    const detail = body.detail ?? body.message;
    return typeof detail === "string" ? detail : response.statusText || "Request failed";
  } catch {
    return response.statusText || "Request failed";
  }
}

function logApiError(action: string, details: unknown) {
  if (process.env.NODE_ENV === "production") return;
  console.warn(`[APFlow] ${action} failed`, details);
}
