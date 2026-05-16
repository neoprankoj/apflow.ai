"use client";

import {
  AlertTriangle,
  Bell,
  Bot,
  CheckCircle2,
  Clock3,
  FileText,
  Loader2,
  LogIn,
  MessageSquare,
  ScanText,
  ShieldCheck,
  UserRound
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppLayout } from "../components/layout/app-layout";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
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
import { ApprovalInbox } from "./approval-inbox";
import { InvoiceUploadPanel } from "./invoice-upload-panel";

const DEMO_EMAIL = "demo-owner@apflow.local";
const DEMO_PASSWORD = "password-123";
const DEMO_TENANT_NAME = "APFlow Demo Tenant";
const DEMO_TENANT_SLUG = "apflow-demo";

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

type WorkflowState = {
  workflow_id: string;
  state: string;
  status: string;
  current_agent: string | null;
};

type ReviewTask = {
  task_id: string;
  status: string;
  issues: Array<{ field_name: string; issue_type: string; message: string; confidence?: number }>;
};

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
  token_type?: string;
  user?: { email: string; full_name: string };
  tenant?: { id: string; name: string; slug: string };
  role?: string;
  permissions?: string[];
  email?: string;
  password?: string;
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

type OCRProviderStatus = {
  provider: string;
  configured: boolean;
  status: string;
  selected: boolean;
};

type ReadyStatus = {
  status: string;
  auth_enabled: boolean;
  demo_mode: boolean;
  checks: Record<string, { status?: string; provider?: string; mode?: string }>;
};

type DashboardData = {
  invoices: InvoiceRecord[];
  approvals: ApprovalTask[];
  notifications: NotificationEvent[];
  workflows: WorkflowState[];
  reviewTasks: ReviewTask[];
  adminUsers: AdminUser[];
  vendorAccess: VendorAccess | null;
  vendorInvoices: VendorInvoice[];
};

const emptyDashboardData: DashboardData = {
  invoices: [],
  approvals: [],
  notifications: [],
  workflows: [],
  reviewTasks: [],
  adminUsers: [],
  vendorAccess: null,
  vendorInvoices: []
};

const agents = [
  { name: "TenantSecurityAgent", status: "enforcing", icon: ShieldCheck },
  { name: "AuditLoggingAgent", status: "recording", icon: FileText },
  { name: "MonitoringAgent", status: "healthy", icon: CheckCircle2 },
  { name: "ErrorHandlerAgent", status: "standing by", icon: AlertTriangle },
  { name: "APWorkflowOrchestratorAgent", status: "dispatching", icon: Bot }
];

export default function Dashboard() {
  const apiBaseUrl = getApiBaseUrl();
  const [authStatus, setAuthStatus] = useState<AuthStatus>("unauthenticated");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState<ReadyStatus | null>(null);
  const [ocrProviders, setOcrProviders] = useState<OCRProviderStatus[]>([]);
  const [mockOcrStatus, setMockOcrStatus] = useState<{ status: string; provider: string }>({
    status: "unknown",
    provider: "mock"
  });
  const [dashboardData, setDashboardData] = useState<DashboardData>(emptyDashboardData);
  const [apiError, setApiError] = useState<string | null>(
    apiBaseUrl ? null : "NEXT_PUBLIC_API_BASE_URL is missing or invalid."
  );
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<string>("overview");
  const [ocrTestMessage, setOcrTestMessage] = useState<string | null>(null);
  const [ocrTestRunning, setOcrTestRunning] = useState(false);
  const [demoResetSignal, setDemoResetSignal] = useState(0);
  const [protectedDataLoading, setProtectedDataLoading] = useState(false);

  const tenantId = currentUser?.tenant.id ?? null;
  const permissions = useMemo(() => new Set(currentUser?.permissions ?? []), [currentUser]);
  const canExportErp = permissions.has("invoice:export_erp");
  const canApproveInvoice = permissions.has("invoice:approve");
  const canAdmin = permissions.has("tenant:admin");
  const canReview = permissions.has("review:correct");
  const canAudit = permissions.has("audit:read");
  const canDemoReset = canAdmin;

  const loadPublicData = useCallback(async () => {
    if (!apiBaseUrl) {
      setApiError("NEXT_PUBLIC_API_BASE_URL is missing or invalid.");
      return;
    }
    try {
      const [readyResult, providersResult, mockStatusResult] = await Promise.all([
        apiFetch<ReadyStatus>(apiBaseUrl, "/ready", { action: "Readiness check" }),
        apiFetch<OCRProviderStatus[]>(apiBaseUrl, "/ocr/providers", { action: "OCR provider status" }),
        apiFetch<{ status: string; provider: string }>(
          apiBaseUrl,
          "/ocr/test-provider?provider_name=mock",
          { action: "Mock OCR status" }
        )
      ]);
      setReady(readyResult);
      setOcrProviders(providersResult);
      setMockOcrStatus(mockStatusResult);
      setApiError(null);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API unavailable: failed to fetch");
    }
  }, [apiBaseUrl]);

  const loadProtectedData = useCallback(
    async (token: string, user: CurrentUser) => {
      if (!apiBaseUrl) return;
      setProtectedDataLoading(true);
      try {
        const query = `tenant_id=${user.tenant.id}`;
        const userPermissions = new Set(user.permissions);
        const [invoices, approvals, notifications, workflows, reviewTasks, adminUsers] = await Promise.allSettled([
          apiFetch<InvoiceRecord[]>(apiBaseUrl, `/invoices?${query}`, { token, action: "List invoices" }),
          apiFetch<ApprovalTask[]>(apiBaseUrl, `/invoices/approval-tasks?${query}`, {
            token,
            action: "List approval tasks"
          }),
          apiFetch<NotificationEvent[]>(apiBaseUrl, `/invoices/notification-events?${query}`, {
            token,
            action: "List notification events"
          }),
          apiFetch<WorkflowState[]>(apiBaseUrl, `/invoices/workflows?${query}`, {
            token,
            action: "List workflow states"
          }),
          apiFetch<ReviewTask[]>(apiBaseUrl, `/review/tasks?${query}`, {
            token,
            action: "List review tasks"
          }),
          userPermissions.has("tenant:admin")
            ? apiFetch<AdminUser[]>(apiBaseUrl, "/admin/users", { token, action: "List tenant users" })
            : Promise.resolve([])
          ]);

        const refreshErrors = [
          refreshErrorMessage(invoices, "Invoice list failed; other dashboard data remains available."),
          refreshErrorMessage(approvals, "Approval task list failed; other dashboard data remains available."),
          refreshErrorMessage(notifications, "Notification list failed; other dashboard data remains available."),
          refreshErrorMessage(workflows, "Workflow state list failed; current invoice state remains available."),
          refreshErrorMessage(reviewTasks, "Review task list failed; other dashboard data remains available."),
          refreshErrorMessage(adminUsers, "Tenant user list failed; other dashboard data remains available.")
        ].filter((message): message is string => Boolean(message));

        let vendorAccess: VendorAccess | null = null;
        let vendorInvoices: VendorInvoice[] = [];
        try {
          vendorAccess = await apiFetch<VendorAccess>(apiBaseUrl, "/vendor/access", {
            method: "POST",
            headers: { "content-type": "application/json" },
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

        setDashboardData((current) => ({
          invoices: invoices.status === "fulfilled" ? invoices.value : current.invoices,
          approvals: approvals.status === "fulfilled" ? approvals.value : current.approvals,
          notifications: notifications.status === "fulfilled" ? notifications.value : current.notifications,
          workflows: workflows.status === "fulfilled" ? workflows.value : current.workflows,
          reviewTasks: reviewTasks.status === "fulfilled" ? reviewTasks.value : current.reviewTasks,
          adminUsers: adminUsers.status === "fulfilled" ? adminUsers.value : current.adminUsers,
          vendorAccess,
          vendorInvoices
        }));
        setApiError(refreshErrors.length ? refreshErrors.join(" ") : null);
      } finally {
        setProtectedDataLoading(false);
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
      setDashboardData(emptyDashboardData);
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
          headers: { "content-type": "application/json" },
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
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
          action: "Demo login"
        });
      }

      let token = tokenResponse.access_token;
      if (!token && tokenResponse.email && tokenResponse.password) {
        const loginResponse = await apiFetch<TokenResponse>(apiBaseUrl, "/auth/login", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email: tokenResponse.email, password: tokenResponse.password }),
          action: "Demo login"
        });
        token = loginResponse.access_token;
      }
      if (!token) {
        throw new ApiRequestError("Demo login failed: backend did not return an access token");
      }

      setStoredToken(token);
      const user = await apiFetch<CurrentUser>(apiBaseUrl, "/auth/me", {
        token,
        action: "Load current user"
      });
      setAccessToken(token);
      setCurrentUser(user);
      setAuthStatus("authenticated");
      setSessionMessage("Signed in.");
      await loadProtectedData(token, user);
    } catch (error) {
      clearStoredToken();
      setAccessToken(null);
      setCurrentUser(null);
      setDashboardData(emptyDashboardData);
      setAuthStatus("failed");
      setSessionMessage(error instanceof Error ? error.message : "Demo login failed.");
    }
  }

  function signOut() {
    clearStoredToken();
    setAccessToken(null);
    setCurrentUser(null);
    setDashboardData(emptyDashboardData);
    setAuthStatus("unauthenticated");
    setSessionMessage("Signed out.");
  }

  async function testOcrProvider(providerName = "azure") {
    if (!apiBaseUrl) {
      setOcrTestMessage("OCR provider test failed: NEXT_PUBLIC_API_BASE_URL is missing or invalid.");
      return;
    }
    setOcrTestRunning(true);
    setOcrTestMessage(`Testing ${providerName} OCR provider...`);
    try {
      const result = await apiFetch<Record<string, unknown>>(
        apiBaseUrl,
        `/ocr/test-provider?provider_name=${encodeURIComponent(providerName)}`,
        { action: `Test ${providerName} OCR provider` }
      );
      const status = typeof result.status === "string" ? result.status : "unknown";
      const detail = typeof result.detail === "string" ? result.detail : "";
      setOcrTestMessage(`${providerName} OCR provider status: ${status}${detail ? ` - ${detail}` : ""}`);
      await loadPublicData();
    } catch (error) {
      setOcrTestMessage(error instanceof Error ? error.message : `${providerName} OCR provider test failed.`);
    } finally {
      setOcrTestRunning(false);
    }
  }

  const { invoices, approvals, notifications, workflows, reviewTasks, adminUsers, vendorAccess, vendorInvoices } =
    dashboardData;
  const pendingApprovals = approvals.filter((task) => task.status === "pending");
  const duplicateWarnings = notifications.filter((event) => event.notification_type === "duplicate_detected");
  const highRiskInvoices = notifications.filter((event) => event.notification_type === "invoice_blocked");
  const openReviewTasks = reviewTasks.filter((task) => task.status === "review_required");
  const lowConfidenceTasks = reviewTasks.filter((task) =>
    task.issues.some((issue) => issue.issue_type === "low_confidence")
  );
  const recentInvoices = invoices.slice(-6).reverse();
  const recentNotifications = notifications.slice(-5).reverse();
  const recentWorkflows = workflows.slice(-5).reverse();
  const recentReviewTasks = reviewTasks.slice(-5).reverse();
  const selectedOcrProvider = ocrProviders.find((provider) => provider.selected);
  const azureOcrProvider = ocrProviders.find((provider) => provider.provider === "azure");
  const ocrSpaceProvider = ocrProviders.find((provider) => provider.provider === "ocr_space");
  const isSignedIn = authStatus === "authenticated" && Boolean(accessToken && currentUser);
  const unauthorized = ready?.auth_enabled && !isSignedIn;
  const navItems = [
    { id: "overview", label: "Overview" },
    { id: "upload-invoice", label: "Upload Invoice" },
    { id: "ocr-review", label: "OCR Review" },
    { id: "approval-inbox", label: "Approval Inbox" },
    { id: "approvals", label: "Approvals" },
    { id: "erp-export", label: "ERP Export" },
    { id: "vendor-portal-preview", label: "Vendor Portal Preview" },
    { id: "admin", label: "Admin" }
  ];
  const selectedProviderName = selectedOcrProvider?.provider ?? "mock";
  const ocrTestProviderName = selectedProviderName === "mock" ? "ocr_space" : selectedProviderName;
  const ocrGuidance =
    selectedProviderName === "azure"
      ? azureOcrProvider?.configured
        ? "Azure OCR ready. Uploaded PDFs will use Azure while OCR_PROVIDER=azure."
        : "Azure OCR credentials are missing. Set OCR_PROVIDER=azure, AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT, and AZURE_DOCUMENT_INTELLIGENCE_KEY."
      : selectedProviderName === "ocr_space"
        ? ocrSpaceProvider?.configured
          ? "OCR.space OCR is selected. Uploaded PDFs/images will use OCR.space while OCR_PROVIDER=ocr_space."
          : "OCR.space API key missing. Set OCR_SPACE_API_KEY in .env.staging."
        : "Mock OCR is active. Set OCR_PROVIDER=ocr_space and OCR_SPACE_API_KEY to test OCR.space, or use Azure credentials to test Azure.";

  return (
    <AppLayout
      actions={
        isSignedIn ? (
          <Button onClick={signOut} variant="secondary">
            Sign out
          </Button>
        ) : (
          <Button disabled={!apiBaseUrl || authStatus === "authenticating"} onClick={demoLogin} variant="primary">
            {authStatus === "authenticating" ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
            Demo login
          </Button>
        )
      }
      activeSection={activeSection}
      aside={
        <>
          <Card>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <UserRound className="h-4 w-4 text-primary" />
                <h2 className="text-base font-semibold">Tenant Session</h2>
              </div>
              <div className="space-y-2 text-sm">
                <div>
                  <p className="font-medium">
                    {isSignedIn ? currentUser?.user.full_name : authStatus === "authenticating" ? "Signing in" : "Not signed in"}
                  </p>
                  <p className="text-xs text-muted">
                    {isSignedIn
                      ? currentUser?.user.email
                      : sessionMessage ?? "Sign in required for upload/process actions."}
                  </p>
                </div>
                <div className="flex items-center justify-between">
                  <span>Status</span>
                  <strong>{isSignedIn ? "Signed in" : authStatus.replaceAll("_", " ")}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Tenant</span>
                  <strong>{currentUser?.tenant.name ?? currentUser?.tenant.id ?? "None"}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Role</span>
                  <strong>{currentUser?.membership.role ?? "none"}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>API</span>
                  <strong>{ready?.status ?? "unavailable"}</strong>
                </div>
                {!isSignedIn ? (
                  <Button
                    className="mt-2 w-full"
                    disabled={!apiBaseUrl || authStatus === "authenticating"}
                    onClick={demoLogin}
                    variant="primary"
                  >
                    Demo login
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <div className="mb-3 flex items-center gap-2">
                <Clock3 className="h-4 w-4 text-primary" />
                <h2 className="text-base font-semibold">Agent Runtime</h2>
              </div>
              <div className="space-y-3">
                {agents.map((agent) => {
                  const Icon = agent.icon;
                  return (
                    <div className="flex items-center gap-3" key={agent.name}>
                      <Icon className="h-4 w-4 text-muted" />
                      <div>
                        <p className="text-sm font-medium">{agent.name}</p>
                        <p className="text-xs text-muted">{agent.status}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <div className="mb-3 flex items-center gap-2">
                <ScanText className="h-4 w-4 text-primary" />
                <h2 className="text-base font-semibold">OCR Status</h2>
              </div>
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span>Selected</span>
                  <strong>{selectedOcrProvider?.provider ?? "mock"}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Mode</span>
                  <strong>{selectedOcrProvider?.configured ? "configured" : "unconfigured/safe"}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Selected status</span>
                  <strong>{selectedOcrProvider?.status ?? "unknown"}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Azure</span>
                  <strong>{azureOcrProvider?.configured ? "configured" : azureOcrProvider?.status ?? "unknown"}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>OCR.space</span>
                  <strong>{ocrSpaceProvider?.configured ? "configured" : ocrSpaceProvider?.status ?? "unknown"}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Mock status</span>
                  <strong>{mockOcrStatus.status}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Review queue</span>
                  <strong>{openReviewTasks.length}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Correction permission</span>
                  <strong>{canReview ? "enabled" : "read only"}</strong>
                </div>
                <div className="rounded-md border border-border bg-background px-3 py-2 text-xs text-muted">
                  {ocrGuidance}
                </div>
                {ocrTestMessage ? (
                  <div className="rounded-md border border-border px-3 py-2 text-xs text-muted">{ocrTestMessage}</div>
                ) : null}
                <Button
                  className="w-full"
                  disabled={ocrTestRunning || !apiBaseUrl}
                  onClick={() => void testOcrProvider(ocrTestProviderName)}
                  variant="secondary"
                >
                  {ocrTestRunning ? `Testing ${ocrTestProviderName} OCR...` : `Test ${ocrTestProviderName} Provider`}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <div className="mb-3 flex items-center gap-2">
                <Bell className="h-4 w-4 text-primary" />
                <h2 className="text-base font-semibold">Recent Notifications</h2>
              </div>
              <div className="space-y-3 text-sm">
                {recentNotifications.length ? (
                  recentNotifications.map((event) => (
                    <div className="border-b border-border pb-3 last:border-0 last:pb-0" key={event.notification_id}>
                      <p className="font-medium">{event.notification_type.replaceAll("_", " ")}</p>
                      <p className="text-xs text-muted">
                        {event.recipient_role} - {event.status} via {event.channel}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted">
                    {isSignedIn ? "No notification events recorded yet." : "Sign in to load notifications."}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <h2 className="text-base font-semibold">Risk Watch</h2>
              <div className="mt-3 space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span>Likely duplicates</span>
                  <strong>{duplicateWarnings.length}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Blocked invoices</span>
                  <strong>{highRiskInvoices.length}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Pending reviews</span>
                  <strong>{pendingApprovals.length}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Audit access</span>
                  <strong>{canAudit ? "enabled" : "hidden"}</strong>
                </div>
              </div>
            </CardContent>
          </Card>

          {canAdmin ? (
            <Card className="scroll-mt-6" id="admin">
              <CardContent>
                <h2 className="text-base font-semibold">Tenant Users</h2>
                <div className="mt-3 space-y-3 text-sm">
                  {adminUsers.length ? (
                    adminUsers.map((item) => (
                      <div className="border-b border-border pb-3 last:border-0 last:pb-0" key={item.user.id}>
                        <p className="font-medium">{item.user.full_name}</p>
                        <p className="text-xs text-muted">
                          {item.role} - {item.is_active ? "active" : "inactive"}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-muted">No tenant users returned.</p>
                  )}
                </div>
              </CardContent>
            </Card>
          ) : null}

          {canAdmin && apiBaseUrl ? (
            <DemoResetButton
              accessToken={accessToken}
              apiBaseUrl={apiBaseUrl}
              canReset={canDemoReset}
              onResetComplete={() => {
                setDemoResetSignal((current) => current + 1);
                if (accessToken && currentUser) void loadProtectedData(accessToken, currentUser);
              }}
            />
          ) : null}
        </>
      }
      breadcrumbs={["Operations"]}
      navItems={navItems}
      onSectionChange={setActiveSection}
      subtitle="Private demo health and workload summary"
      title="Dashboard"
    >
          {apiError ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              {apiError}
            </div>
          ) : null}
          {unauthorized ? (
            <div className="flex items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <span>Sign in required for upload, processing, ERP export, review, and admin actions.</span>
              <Button
                className="border-amber-300"
                disabled={!apiBaseUrl || authStatus === "authenticating"}
                onClick={demoLogin}
                size="sm"
                variant="secondary"
              >
                Demo login
              </Button>
            </div>
          ) : null}
          {ready && ready.status !== "ready" ? (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              Runtime is {ready.status}. Some checks may be degraded.
            </div>
          ) : null}

          <section className="scroll-mt-6 space-y-3" id="overview">
            <SectionHeading title="Overview" subtitle="Private demo health and workload summary" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {[
                ["Total invoices", invoices.length.toString()],
                ["Pending approvals", pendingApprovals.length.toString()],
                ["Review required", openReviewTasks.length.toString()],
                ["Low confidence", lowConfidenceTasks.length.toString()]
              ].map(([label, value]) => (
                <Card key={label}>
                  <CardContent>
                    <p className="text-sm text-muted">{label}</p>
                    <p className="mt-2 text-2xl font-semibold">{value}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>

          <div id="upload-invoice-top">
            <InvoiceUploadPanel
              accessToken={accessToken}
              apiBaseUrl={apiBaseUrl}
              authStatus={authStatus}
              canApproveInvoice={canApproveInvoice}
              canCorrectReview={canReview}
              canExportErp={canExportErp}
              onDemoLogin={demoLogin}
              onWorkflowUpdated={() => {
                if (accessToken && currentUser) {
                  return loadProtectedData(accessToken, currentUser);
                }
              }}
              resetSignal={demoResetSignal}
              selectedOcrProvider={selectedOcrProvider?.provider ?? "mock"}
              selectedOcrStatus={selectedOcrProvider?.status ?? "ok"}
              tenantId={tenantId}
            />
          </div>

          <ApprovalInbox
            accessToken={accessToken}
            apiBaseUrl={apiBaseUrl}
            approvals={approvals}
            canApproveInvoice={canApproveInvoice}
            canExportErp={canExportErp}
            invoices={invoices}
            isLoading={protectedDataLoading}
            notifications={notifications}
            onRefresh={() => {
              if (accessToken && currentUser) {
                return loadProtectedData(accessToken, currentUser);
              }
            }}
            tenantId={tenantId}
          />

          <section className="scroll-mt-6 space-y-3" id="approvals">
            <SectionHeading title="Approvals" subtitle="Recent invoices, review work, and workflow states" />
            <Card>
              <CardHeader className="flex items-center justify-between">
                <h2 className="text-base font-semibold">Invoice Queue</h2>
                <span className="text-xs text-muted">{tenantId ? "Tenant scoped" : "Sign in required"}</span>
              </CardHeader>
              <div className="divide-y divide-border">
                {recentInvoices.length ? (
                  recentInvoices.map((item) => (
                    <div
                      className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-[140px_1fr_120px_150px]"
                      key={item.invoice_id}
                    >
                      <span className="font-medium">{item.canonical_invoice.invoice_number}</span>
                      <span>{item.canonical_invoice.supplier_name}</span>
                      <span>{money(item.canonical_invoice.grand_total, item.canonical_invoice.currency)}</span>
                      <span className="text-muted">Captured</span>
                    </div>
                  ))
                ) : (
                  <CardContent>
                    <EmptyState
                      description={isSignedIn ? "No invoices have been captured for this tenant yet." : "Sign in to load tenant invoices."}
                      title="No invoices to review"
                    />
                  </CardContent>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader>
                <h2 className="text-base font-semibold">Recent Review Tasks</h2>
              </CardHeader>
              <div className="divide-y divide-border">
                {recentReviewTasks.length ? (
                  recentReviewTasks.map((task) => (
                    <div className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-[150px_1fr_120px]" key={task.task_id}>
                      <span className="font-medium">{task.status.replaceAll("_", " ")}</span>
                      <span>{task.issues[0]?.message ?? "No field issue"}</span>
                      <span className="text-muted">{task.issues.length} issues</span>
                    </div>
                  ))
                ) : (
                  <CardContent>
                    <EmptyState
                      description={isSignedIn ? "There are no human review tasks waiting right now." : "Sign in to load review tasks."}
                      title="No review tasks"
                    />
                  </CardContent>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader>
                <h2 className="text-base font-semibold">Recent Workflow Statuses</h2>
              </CardHeader>
              <div className="divide-y divide-border">
                {recentWorkflows.length ? (
                  recentWorkflows.map((workflow) => (
                    <div className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-[1fr_120px_180px]" key={workflow.workflow_id}>
                      <span className="font-medium">{workflow.state}</span>
                      <span>{workflow.status}</span>
                      <span className="text-muted">{workflow.current_agent ?? "none"}</span>
                    </div>
                  ))
                ) : (
                  <CardContent>
                    <EmptyState
                      description={isSignedIn ? "Workflow activity will appear after invoices are processed." : "Sign in to load workflow states."}
                      title="No workflow states"
                    />
                  </CardContent>
                )}
              </div>
            </Card>
          </section>

      <Card>
        <CardContent className="grid gap-5 lg:grid-cols-[280px_1fr_320px]">
          <div>
            <div className="mb-3 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <h2 className="text-base font-semibold">Vendor Portal</h2>
            </div>
            <Button disabled={!vendorAccess} variant="secondary">
              Demo vendor session
            </Button>
            <p className="mt-3 text-xs text-muted">
              {vendorAccess?.email ?? (isSignedIn ? "Vendor access is not ready." : "Sign in to prepare vendor preview.")}
            </p>
          </div>

          <div className="rounded-md border border-border">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-base font-semibold">Vendor Invoices</h3>
            </div>
            <div className="divide-y divide-border">
              {vendorInvoices.length ? (
                vendorInvoices.map((invoice) => (
                  <div
                    className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-[140px_1fr_150px_120px]"
                    key={invoice.invoice_id}
                  >
                    <span className="font-medium">{invoice.invoice_number}</span>
                    <span>{invoice.status.replaceAll("_", " ")}</span>
                    <span>{money(invoice.grand_total, invoice.currency)}</span>
                    <span className="text-muted">{invoice.payment_status ?? "not scheduled"}</span>
                  </div>
                ))
              ) : (
                <div className="px-4 py-6 text-sm text-muted">
                  {isSignedIn ? "No vendor-visible invoices." : "Sign in before loading vendor-safe invoices."}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-5">
            <div className="rounded-md border border-border p-4">
              <div className="mb-3 flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" />
                <h3 className="text-base font-semibold">Vendor Message</h3>
              </div>
              <textarea
                className="min-h-24 w-full resize-none rounded-md border border-border p-3 text-sm"
                defaultValue="Please confirm the expected payment date."
              />
              <Button className="mt-3" disabled={!vendorAccess} variant="primary">
                Submit
              </Button>
            </div>
            <div className="rounded-md border border-border p-4">
              <h3 className="text-base font-semibold">Status Chat</h3>
              <div className="mt-3 rounded-md border border-border px-3 py-2 text-sm text-muted">
                {vendorAccess ? "What is the payment status?" : "Vendor access must be created first."}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </AppLayout>
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

function money(value: number, currency: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 2
  }).format(value || 0);
}

function refreshErrorMessage<T>(result: PromiseSettledResult<T>, prefix: string) {
  if (result.status === "fulfilled") return null;
  const detail = result.reason instanceof Error ? result.reason.message : "Dashboard data failed to load.";
  return `${prefix} ${detail}`;
}
