"use client";

import { AlertTriangle, Bell, CheckCircle2, Loader2, LogIn, ScanText, ShieldCheck, UserRound } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DemoResetButton } from "./demo-reset-button";
import {
  ApiRequestError,
  AuthStatus,
  apiFetch,
  clearStoredToken,
  getApiBaseUrl,
  getStoredToken,
  setStoredToken
} from "./frontend-api";
import { InvoiceUploadPanel } from "./invoice-upload-panel";

const DEMO_EMAIL = "demo-owner@apflow.local";
const DEMO_PASSWORD = "password-123";
const DEMO_TENANT_NAME = "APFlow Demo Tenant";
const DEMO_TENANT_SLUG = "apflow-demo";

type CurrentUser = {
  user: { id: string; email: string; full_name: string };
  tenant: { id: string; name: string; slug: string };
  membership: { role: string };
  permissions: string[];
  auth_enabled: boolean;
  demo_mode: boolean;
};

type TokenResponse = {
  access_token?: string;
  email?: string;
  password?: string;
};

type ReadyStatus = {
  status: string;
  auth_enabled: boolean;
  demo_mode: boolean;
};

type OCRProviderStatus = {
  provider: string;
  configured: boolean;
  status: string;
  selected: boolean;
};

type InvoiceRecord = {
  invoice_id: string;
  canonical_invoice: {
    invoice_number: string;
    supplier_name: string;
    grand_total: number;
    currency: string;
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
};

type ReviewTask = {
  task_id: string;
  status: string;
  issues: Array<{ field_name: string; issue_type: string; message: string; confidence?: number }>;
};

type AdminUser = {
  user: { id: string; email: string; full_name: string };
  role: string;
  is_active: boolean;
};

type VendorAccess = {
  access_token: string | null;
  email: string;
  vendor_id: string;
};

type VendorInvoice = {
  invoice_id: string;
  invoice_number: string;
  grand_total: number;
  currency: string;
  status: string;
  payment_status: string | null;
};

type DashboardData = {
  invoices: InvoiceRecord[];
  approvals: ApprovalTask[];
  notifications: NotificationEvent[];
  reviewTasks: ReviewTask[];
  adminUsers: AdminUser[];
  vendorAccess: VendorAccess | null;
  vendorInvoices: VendorInvoice[];
};

const emptyDashboardData: DashboardData = {
  invoices: [],
  approvals: [],
  notifications: [],
  reviewTasks: [],
  adminUsers: [],
  vendorAccess: null,
  vendorInvoices: []
};

export default function Dashboard() {
  const apiBaseUrl = getApiBaseUrl();
  const [authStatus, setAuthStatus] = useState<AuthStatus>("unauthenticated");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState<ReadyStatus | null>(null);
  const [ocrProviders, setOcrProviders] = useState<OCRProviderStatus[]>([]);
  const [data, setData] = useState<DashboardData>(emptyDashboardData);
  const [apiError, setApiError] = useState<string | null>(
    apiBaseUrl ? null : "NEXT_PUBLIC_API_BASE_URL is missing or invalid."
  );
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);

  const tenantId = currentUser?.tenant.id ?? null;
  const permissions = useMemo(() => new Set(currentUser?.permissions ?? []), [currentUser]);
  const isSignedIn = authStatus === "authenticated" && Boolean(accessToken && currentUser);
  const canExportErp = permissions.has("invoice:export_erp");
  const canAdmin = permissions.has("tenant:admin");
  const canReview = permissions.has("review:correct");
  const canAudit = permissions.has("audit:read");
  const selectedOcrProvider = ocrProviders.find((provider) => provider.selected);
  const azureOcrProvider = ocrProviders.find((provider) => provider.provider === "azure");

  const loadPublicData = useCallback(async () => {
    if (!apiBaseUrl) {
      setApiError("NEXT_PUBLIC_API_BASE_URL is missing or invalid.");
      return;
    }
    try {
      const [readyResult, providersResult] = await Promise.all([
        apiFetch<ReadyStatus>(apiBaseUrl, "/ready", { action: "Readiness check" }),
        apiFetch<OCRProviderStatus[]>(apiBaseUrl, "/ocr/providers", { action: "OCR provider status" })
      ]);
      setReady(readyResult);
      setOcrProviders(providersResult);
      setApiError(null);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API unavailable: failed to fetch");
    }
  }, [apiBaseUrl]);

  const loadProtectedData = useCallback(
    async (token: string, user: CurrentUser) => {
      if (!apiBaseUrl) return;
      const query = `tenant_id=${user.tenant.id}`;
      const userPermissions = new Set(user.permissions);
      try {
        const [invoices, approvals, notifications, reviewTasks, adminUsers] = await Promise.all([
          apiFetch<InvoiceRecord[]>(apiBaseUrl, `/invoices?${query}`, { token, action: "List invoices" }),
          apiFetch<ApprovalTask[]>(apiBaseUrl, `/invoices/approval-tasks?${query}`, { token, action: "List approval tasks" }),
          apiFetch<NotificationEvent[]>(apiBaseUrl, `/invoices/notification-events?${query}`, {
            token,
            action: "List notification events"
          }),
          apiFetch<ReviewTask[]>(apiBaseUrl, `/review/tasks?${query}`, { token, action: "List review tasks" }),
          userPermissions.has("tenant:admin")
            ? apiFetch<AdminUser[]>(apiBaseUrl, "/admin/users", { token, action: "List tenant users" })
            : Promise.resolve([])
        ]);

        let vendorAccess: VendorAccess | null = null;
        let vendorInvoices: VendorInvoice[] = [];
        try {
          vendorAccess = await apiFetch<VendorAccess>(apiBaseUrl, "/vendor/access", {
            method: "POST",
            body: JSON.stringify({ tenant_id: user.tenant.id, email: "vendor@example.com" }),
            token,
            action: "Create vendor demo access"
          });
          if (vendorAccess.access_token) {
            vendorInvoices = await apiFetch<VendorInvoice[]>(
              apiBaseUrl,
              `/vendor/invoices?${query}&access_token=${encodeURIComponent(vendorAccess.access_token)}`,
              { action: "List vendor invoices" }
            );
          }
        } catch (error) {
          console.warn("[APFlow] Vendor preview setup failed", error);
        }

        setData({ invoices, approvals, notifications, reviewTasks, adminUsers, vendorAccess, vendorInvoices });
      } catch (error) {
        setApiError(error instanceof Error ? error.message : "Dashboard data failed to load.");
      }
    },
    [apiBaseUrl]
  );

  const restoreSession = useCallback(async () => {
    if (!apiBaseUrl) return;
    const storedToken = getStoredToken();
    if (!storedToken) {
      setAuthStatus("unauthenticated");
      return;
    }
    setAuthStatus("authenticating");
    try {
      const user = await apiFetch<CurrentUser>(apiBaseUrl, "/auth/me", {
        token: storedToken,
        action: "Restore session"
      });
      setAccessToken(storedToken);
      setCurrentUser(user);
      setAuthStatus("authenticated");
      setSessionMessage(null);
      await loadProtectedData(storedToken, user);
    } catch (error) {
      clearStoredToken();
      setAccessToken(null);
      setCurrentUser(null);
      setData(emptyDashboardData);
      setAuthStatus("failed");
      setSessionMessage(error instanceof Error ? error.message : "Stored session expired.");
    }
  }, [apiBaseUrl, loadProtectedData]);

  useEffect(() => {
    void loadPublicData();
    void restoreSession();
  }, [loadPublicData, restoreSession]);

  async function demoLogin() {
    if (!apiBaseUrl) {
      setApiError("NEXT_PUBLIC_API_BASE_URL is missing or invalid.");
      return;
    }
    setAuthStatus("authenticating");
    setSessionMessage("Signing in to demo tenant...");
    try {
      let tokenResponse: TokenResponse;
      try {
        tokenResponse = await apiFetch<TokenResponse>(apiBaseUrl, "/auth/register-demo-tenant", {
          method: "POST",
          body: JSON.stringify({
            tenant_name: DEMO_TENANT_NAME,
            tenant_slug: DEMO_TENANT_SLUG,
            email: DEMO_EMAIL,
            full_name: "Demo Owner",
            password: DEMO_PASSWORD
          }),
          action: "Demo login registration"
        });
      } catch (registerError) {
        console.warn("[APFlow] Demo registration unavailable; trying login fallback.", registerError);
        tokenResponse = await apiFetch<TokenResponse>(apiBaseUrl, "/auth/login", {
          method: "POST",
          body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
          action: "Demo login"
        });
      }

      let token = tokenResponse.access_token;
      if (!token && tokenResponse.email && tokenResponse.password) {
        const loginResponse = await apiFetch<TokenResponse>(apiBaseUrl, "/auth/login", {
          method: "POST",
          body: JSON.stringify({ email: tokenResponse.email, password: tokenResponse.password }),
          action: "Demo login"
        });
        token = loginResponse.access_token;
      }
      if (!token) {
        throw new ApiRequestError("Demo login failed: backend did not return an access token");
      }

      setStoredToken(token);
      const user = await apiFetch<CurrentUser>(apiBaseUrl, "/auth/me", { token, action: "Load current user" });
      setAccessToken(token);
      setCurrentUser(user);
      setAuthStatus("authenticated");
      setSessionMessage("Signed in.");
      await loadProtectedData(token, user);
    } catch (error) {
      clearStoredToken();
      setAccessToken(null);
      setCurrentUser(null);
      setData(emptyDashboardData);
      setAuthStatus("failed");
      setSessionMessage(error instanceof Error ? error.message : "Demo login failed.");
    }
  }

  function signOut() {
    clearStoredToken();
    setAccessToken(null);
    setCurrentUser(null);
    setData(emptyDashboardData);
    setAuthStatus("unauthenticated");
    setSessionMessage("Signed out.");
  }

  const pendingApprovals = data.approvals.filter((task) => task.status === "pending");
  const openReviewTasks = data.reviewTasks.filter((task) => task.status === "review_required");
  const lowConfidenceTasks = data.reviewTasks.filter((task) =>
    task.issues.some((issue) => issue.issue_type === "low_confidence")
  );
  const duplicateWarnings = data.notifications.filter((event) => event.notification_type === "duplicate_detected");
  const highRiskInvoices = data.notifications.filter((event) => event.notification_type === "invoice_blocked");
  const recentInvoices = data.invoices.slice(-6).reverse();
  const recentNotifications = data.notifications.slice(-5).reverse();
  const unauthorized = ready?.auth_enabled && !isSignedIn;

  return (
    <main className="min-h-screen">
      <div className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <h1 className="text-xl font-semibold tracking-normal">APFlow AI</h1>
            <p className="text-sm text-muted">Accounts payable operations</p>
          </div>
          {isSignedIn ? (
            <button className="rounded-md border border-border px-3 py-2 text-sm" onClick={signOut} type="button">
              Sign out
            </button>
          ) : (
            <button
              className="inline-flex items-center rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
              disabled={!apiBaseUrl || authStatus === "authenticating"}
              onClick={demoLogin}
              type="button"
            >
              {authStatus === "authenticating" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogIn className="mr-2 h-4 w-4" />}
              Demo login
            </button>
          )}
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-5 lg:grid-cols-[220px_1fr_320px]">
        <nav className="space-y-1 text-sm">
          {["Overview", "Upload Invoice", "OCR Review", "Approvals", "ERP Export", "Vendor Portal Preview", "Admin"].map((item) => (
            <button className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left hover:bg-white" key={item} type="button">
              {item}
            </button>
          ))}
        </nav>

        <section className="space-y-5">
          {apiError ? <Alert tone="error" message={apiError} /> : null}
          {unauthorized ? (
            <div className="flex items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <span>Sign in required for upload, processing, ERP export, review, and admin actions.</span>
              <button
                className="rounded-md border border-amber-300 bg-white px-3 py-2 text-sm disabled:text-muted"
                disabled={!apiBaseUrl || authStatus === "authenticating"}
                onClick={demoLogin}
                type="button"
              >
                Demo login
              </button>
            </div>
          ) : null}
          {ready && ready.status !== "ready" ? <Alert tone="warning" message={`Runtime is ${ready.status}. Some checks may be degraded.`} /> : null}

          <SectionHeading title="Overview" subtitle="Private demo health and workload summary" />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Total invoices" value={data.invoices.length.toString()} />
            <Metric label="Pending approvals" value={pendingApprovals.length.toString()} />
            <Metric label="Review required" value={openReviewTasks.length.toString()} />
            <Metric label="Low confidence" value={lowConfidenceTasks.length.toString()} />
          </div>

          <InvoiceUploadPanel
            accessToken={accessToken}
            apiBaseUrl={apiBaseUrl}
            authStatus={authStatus}
            canExportErp={canExportErp}
            onDemoLogin={demoLogin}
            selectedOcrProvider={selectedOcrProvider?.provider ?? "mock"}
            selectedOcrStatus={selectedOcrProvider?.status ?? "ok"}
            tenantId={tenantId}
          />

          <SectionHeading title="Approvals" subtitle="Recent invoice and review work" />
          <Panel title="Invoice Queue" detail={tenantId ? "Tenant scoped" : "Sign in required"}>
            {recentInvoices.length ? (
              recentInvoices.map((invoice) => (
                <div className="grid gap-3 border-b border-border px-4 py-3 text-sm last:border-0 sm:grid-cols-[140px_1fr_120px]" key={invoice.invoice_id}>
                  <span className="font-medium">{invoice.canonical_invoice.invoice_number}</span>
                  <span>{invoice.canonical_invoice.supplier_name}</span>
                  <span>{money(invoice.canonical_invoice.grand_total, invoice.canonical_invoice.currency)}</span>
                </div>
              ))
            ) : (
              <EmptyState text={isSignedIn ? "No invoices for this tenant." : "Sign in to load tenant invoices."} />
            )}
          </Panel>
        </section>

        <aside className="space-y-5">
          <div className="rounded-md border border-border bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <UserRound className="h-4 w-4 text-[hsl(var(--accent))]" />
              <h2 className="text-base font-semibold">Tenant Session</h2>
            </div>
            <div className="space-y-2 text-sm">
              <div>
                <p className="font-medium">{isSignedIn ? currentUser?.user.full_name : authStatus === "authenticating" ? "Signing in" : "Not signed in"}</p>
                <p className="text-xs text-muted">{isSignedIn ? currentUser?.user.email : sessionMessage ?? "Sign in required for upload/process actions."}</p>
              </div>
              <SessionRow label="Status" value={isSignedIn ? "Signed in" : authStatus.replaceAll("_", " ")} />
              <SessionRow label="Tenant" value={currentUser?.tenant.name ?? currentUser?.tenant.id ?? "None"} />
              <SessionRow label="Role" value={currentUser?.membership.role ?? "none"} />
              <SessionRow label="API" value={ready?.status ?? "unavailable"} />
              {!isSignedIn ? (
                <button className="mt-2 w-full rounded-md bg-black px-3 py-2 text-sm text-white disabled:bg-neutral-300" disabled={!apiBaseUrl || authStatus === "authenticating"} onClick={demoLogin} type="button">
                  Demo login
                </button>
              ) : null}
            </div>
          </div>

          <div className="rounded-md border border-border bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <ScanText className="h-4 w-4 text-[hsl(var(--accent))]" />
              <h2 className="text-base font-semibold">OCR Status</h2>
            </div>
            <div className="space-y-3 text-sm">
              <SessionRow label="Selected" value={selectedOcrProvider?.provider ?? "mock"} />
              <SessionRow label="Selected status" value={selectedOcrProvider?.status ?? "unknown"} />
              <SessionRow label="Azure" value={azureOcrProvider?.configured ? "configured" : azureOcrProvider?.status ?? "unknown"} />
              <SessionRow label="Review queue" value={openReviewTasks.length.toString()} />
              <SessionRow label="Correction" value={canReview ? "enabled" : "read only"} />
            </div>
          </div>

          <div className="rounded-md border border-border bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <Bell className="h-4 w-4 text-[hsl(var(--accent))]" />
              <h2 className="text-base font-semibold">Recent Notifications</h2>
            </div>
            <div className="space-y-3 text-sm">
              {recentNotifications.length ? (
                recentNotifications.map((event) => (
                  <div className="border-b border-border pb-3 last:border-0 last:pb-0" key={event.notification_id}>
                    <p className="font-medium">{event.notification_type.replaceAll("_", " ")}</p>
                    <p className="text-xs text-muted">{event.recipient_role} - {event.status} via {event.channel}</p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted">{isSignedIn ? "No notification events recorded yet." : "Sign in to load notifications."}</p>
              )}
            </div>
          </div>

          <div className="rounded-md border border-border bg-white p-4">
            <h2 className="text-base font-semibold">Risk Watch</h2>
            <div className="mt-3 space-y-3 text-sm">
              <SessionRow label="Likely duplicates" value={duplicateWarnings.length.toString()} />
              <SessionRow label="Blocked invoices" value={highRiskInvoices.length.toString()} />
              <SessionRow label="Audit access" value={canAudit ? "enabled" : "hidden"} />
            </div>
          </div>

          {canAdmin ? (
            <div className="rounded-md border border-border bg-white p-4">
              <h2 className="text-base font-semibold">Tenant Users</h2>
              <div className="mt-3 space-y-3 text-sm">
                {data.adminUsers.length ? data.adminUsers.map((item) => <p key={item.user.id}>{item.user.email} - {item.role}</p>) : <p className="text-muted">No tenant users returned.</p>}
              </div>
            </div>
          ) : null}

          {canAdmin && apiBaseUrl ? (
            <DemoResetButton
              accessToken={accessToken}
              apiBaseUrl={apiBaseUrl}
              canReset={canAdmin}
              onResetComplete={() => {
                if (accessToken && currentUser) void loadProtectedData(accessToken, currentUser);
              }}
            />
          ) : null}
        </aside>
      </div>

      <section className="border-t border-border bg-white">
        <div className="mx-auto grid max-w-7xl gap-5 px-5 py-5 lg:grid-cols-[280px_1fr_320px]">
          <div>
            <div className="mb-3 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-[hsl(var(--accent))]" />
              <h2 className="text-base font-semibold">Vendor Portal</h2>
            </div>
            <button className="rounded-md border border-border px-3 py-2 text-sm" disabled={!data.vendorAccess} type="button">Demo vendor session</button>
            <p className="mt-3 text-xs text-muted">{data.vendorAccess?.email ?? (isSignedIn ? "Vendor access is not ready." : "Sign in to prepare vendor preview.")}</p>
          </div>
          <Panel title="Vendor Invoices">
            {data.vendorInvoices.length ? (
              data.vendorInvoices.map((invoice) => (
                <div className="grid gap-3 border-b border-border px-4 py-3 text-sm last:border-0 sm:grid-cols-[140px_1fr_150px]" key={invoice.invoice_id}>
                  <span className="font-medium">{invoice.invoice_number}</span>
                  <span>{invoice.status.replaceAll("_", " ")}</span>
                  <span>{money(invoice.grand_total, invoice.currency)}</span>
                </div>
              ))
            ) : (
              <EmptyState text={isSignedIn ? "No vendor-visible invoices." : "Sign in before loading vendor-safe invoices."} />
            )}
          </Panel>
        </div>
      </section>
    </main>
  );
}

function Alert({ tone, message }: { tone: "error" | "warning"; message: string }) {
  const styles = tone === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-800";
  return <div className={`rounded-md border px-4 py-3 text-sm ${styles}`}>{message}</div>;
}

function EmptyState({ text }: { text: string }) {
  return <div className="px-4 py-6 text-sm text-muted">{text}</div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-white p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function Panel({ title, detail, children }: { title: string; detail?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-white">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-base font-semibold">{title}</h2>
        {detail ? <span className="text-xs text-muted">{detail}</span> : null}
      </div>
      <div>{children}</div>
    </div>
  );
}

function SectionHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="text-sm text-muted">{subtitle}</p>
    </div>
  );
}

function SessionRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span>{label}</span>
      <strong className="truncate text-right">{value}</strong>
    </div>
  );
}

function money(value: number, currency: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 2
  }).format(value || 0);
}
