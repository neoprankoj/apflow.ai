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

export type PrioritySyncPreviewKind = "vendors" | "purchase_orders";

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

export function previewPrioritySync(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  kind: PrioritySyncPreviewKind,
  limit = 10
) {
  return apiFetch<PrioritySyncPreviewResponse>(apiBaseUrl, "/erp/priority/sync-preview", {
    method: "POST",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, kind, limit }),
    action: kind === "vendors" ? "Preview Priority vendor sync" : "Preview Priority purchase order sync"
  });
}

export function previewPriorityVendorSync(apiBaseUrl: string, token: string, tenantId: string) {
  return previewPrioritySync(apiBaseUrl, token, tenantId, "vendors");
}

export function previewPriorityPurchaseOrderSync(apiBaseUrl: string, token: string, tenantId: string) {
  return previewPrioritySync(apiBaseUrl, token, tenantId, "purchase_orders");
}

export function generatePriorityImportPlan(
  apiBaseUrl: string,
  token: string,
  tenantId: string,
  kind: PrioritySyncPreviewKind,
  limit = 10
) {
  return apiFetch<PriorityImportPlanResponse>(apiBaseUrl, "/erp/priority/import-plan", {
    method: "POST",
    token,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tenant_id: tenantId, kind, limit }),
    action: kind === "vendors" ? "Generate Priority vendor import plan" : "Generate Priority purchase order import plan"
  });
}

export function generatePriorityVendorImportPlan(apiBaseUrl: string, token: string, tenantId: string) {
  return generatePriorityImportPlan(apiBaseUrl, token, tenantId, "vendors");
}

export function generatePriorityPurchaseOrderImportPlan(apiBaseUrl: string, token: string, tenantId: string) {
  return generatePriorityImportPlan(apiBaseUrl, token, tenantId, "purchase_orders");
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
