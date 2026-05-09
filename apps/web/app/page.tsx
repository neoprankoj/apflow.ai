import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Bot,
  CheckCircle2,
  MessageSquare,
  Clock3,
  FileText,
  ScanText,
  Search,
  ShieldCheck,
  UserRound
} from "lucide-react";
import { InvoiceUploadPanel } from "./invoice-upload-panel";

export const dynamic = "force-dynamic";

const DEMO_TENANT_ID = "11111111-1111-1111-1111-111111111111";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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
  user: { email: string; full_name: string };
  tenant: { id: string; name: string; slug: string };
  membership: { role: string };
  permissions: string[];
  demo_mode: boolean;
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

async function fetchJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

async function postJson<T>(path: string, payload: unknown, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store"
    });
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

const agents = [
  { name: "TenantSecurityAgent", status: "enforcing", icon: ShieldCheck },
  { name: "AuditLoggingAgent", status: "recording", icon: FileText },
  { name: "MonitoringAgent", status: "healthy", icon: CheckCircle2 },
  { name: "ErrorHandlerAgent", status: "standing by", icon: AlertTriangle },
  { name: "APWorkflowOrchestratorAgent", status: "dispatching", icon: Bot }
];

function money(value: number, currency: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 2
  }).format(value || 0);
}

export default async function Dashboard() {
  const query = `tenant_id=${DEMO_TENANT_ID}`;
  const currentUser = await fetchJson<CurrentUser | null>("/auth/me", null);
  const [invoices, approvals, notifications, workflows] = await Promise.all([
    fetchJson<InvoiceRecord[]>(`/invoices?${query}`, []),
    fetchJson<ApprovalTask[]>(`/invoices/approval-tasks?${query}`, []),
    fetchJson<NotificationEvent[]>(`/invoices/notification-events?${query}`, []),
    fetchJson<WorkflowState[]>(`/invoices/workflows?${query}`, [])
  ]);
  const [reviewTasks, ocrProviders, mockOcrStatus] = await Promise.all([
    fetchJson<ReviewTask[]>(`/review/tasks?${query}`, []),
    fetchJson<OCRProviderStatus[]>("/ocr/providers", []),
    fetchJson<{ status: string; provider: string }>("/ocr/test-provider?provider_name=mock", {
      status: "unknown",
      provider: "mock"
    })
  ]);
  const adminUsers = currentUser?.permissions.includes("tenant:admin")
    ? await fetchJson<AdminUser[]>("/admin/users", [])
    : [];
  const vendorAccess = await postJson<VendorAccess | null>(
    "/vendor/access",
    { tenant_id: DEMO_TENANT_ID, email: "vendor@example.com" },
    null
  );
  const vendorInvoices = vendorAccess?.access_token
    ? await fetchJson<VendorInvoice[]>(
        `/vendor/invoices?${query}&access_token=${encodeURIComponent(vendorAccess.access_token)}`,
        []
      )
    : [];

  const pendingApprovals = approvals.filter((task) => task.status === "pending");
  const duplicateWarnings = notifications.filter(
    (event) => event.notification_type === "duplicate_detected"
  );
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

  return (
    <main className="min-h-screen">
      <div className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <h1 className="text-xl font-semibold tracking-normal">APFlow AI</h1>
            <p className="text-sm text-muted">Accounts payable operations</p>
          </div>
          <div className="flex items-center gap-3">
            <button className="rounded-md border border-border px-3 py-2 text-sm" type="button">
              {currentUser?.demo_mode ? "Demo session active" : "Demo login"}
            </button>
            <div className="hidden items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted sm:flex">
              <Search className="h-4 w-4" />
              <span>Search invoices, vendors, POs</span>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-5 lg:grid-cols-[220px_1fr_320px]">
        <nav className="space-y-1 text-sm">
          {["Inbox", "Approvals", "Exceptions", "Vendors", "Reports", "Settings"].map((item) => (
            <button
              className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left hover:bg-white"
              key={item}
              type="button"
            >
              {item}
              {item === "Inbox" ? <ArrowRight className="h-4 w-4" /> : null}
            </button>
          ))}
        </nav>

        <section className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Total invoices", invoices.length.toString()],
              ["Pending approvals", pendingApprovals.length.toString()],
              ["Review required", openReviewTasks.length.toString()],
              ["Low confidence", lowConfidenceTasks.length.toString()]
            ].map(([label, value]) => (
              <div className="rounded-md border border-border bg-white p-4" key={label}>
                <p className="text-sm text-muted">{label}</p>
                <p className="mt-2 text-2xl font-semibold">{value}</p>
              </div>
            ))}
          </div>

          <InvoiceUploadPanel
            apiBaseUrl={API_BASE_URL}
            selectedOcrProvider={selectedOcrProvider?.provider ?? "mock"}
            selectedOcrStatus={selectedOcrProvider?.status ?? "ok"}
            tenantId={DEMO_TENANT_ID}
          />

          <div className="rounded-md border border-border bg-white">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Invoice Queue</h2>
              <span className="text-xs text-muted">Tenant scoped</span>
            </div>
            <div className="divide-y divide-border">
              {recentInvoices.length ? (
                recentInvoices.map((item) => (
                  <div
                    className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-[140px_1fr_120px_150px]"
                    key={item.invoice_id}
                  >
                    <span className="font-medium">{item.canonical_invoice.invoice_number}</span>
                    <span>{item.canonical_invoice.supplier_name}</span>
                    <span>
                      {money(item.canonical_invoice.grand_total, item.canonical_invoice.currency)}
                    </span>
                    <span className="text-muted">Captured</span>
                  </div>
                ))
              ) : (
                <div className="px-4 py-6 text-sm text-muted">No invoices for the demo tenant.</div>
              )}
            </div>
          </div>

          <div className="rounded-md border border-border bg-white">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Recent Review Tasks</h2>
            </div>
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
                <div className="px-4 py-6 text-sm text-muted">No review tasks for the demo tenant.</div>
              )}
            </div>
          </div>

          <div className="rounded-md border border-border bg-white">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Recent Workflow Statuses</h2>
            </div>
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
                <div className="px-4 py-6 text-sm text-muted">No workflow states recorded yet.</div>
              )}
            </div>
          </div>
        </section>

        <aside className="space-y-5">
          <div className="rounded-md border border-border bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <UserRound className="h-4 w-4 text-[hsl(var(--accent))]" />
              <h2 className="text-base font-semibold">Tenant Session</h2>
            </div>
            <div className="space-y-2 text-sm">
              <div>
                <p className="font-medium">{currentUser?.user.full_name ?? "Not signed in"}</p>
                <p className="text-xs text-muted">{currentUser?.user.email ?? "Demo mode unavailable"}</p>
              </div>
              <div className="flex items-center justify-between">
                <span>Tenant</span>
                <strong>{currentUser?.tenant.name ?? "None"}</strong>
              </div>
              <div className="flex items-center justify-between">
                <span>Role</span>
                <strong>{currentUser?.membership.role ?? "none"}</strong>
              </div>
            </div>
          </div>

          <div className="rounded-md border border-border bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <Clock3 className="h-4 w-4 text-[hsl(var(--accent))]" />
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
          </div>

          <div className="rounded-md border border-border bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <ScanText className="h-4 w-4 text-[hsl(var(--accent))]" />
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
                <span>Mock status</span>
                <strong>{mockOcrStatus.status}</strong>
              </div>
              <div className="flex items-center justify-between">
                <span>Review queue</span>
                <strong>{openReviewTasks.length}</strong>
              </div>
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
                    <p className="text-xs text-muted">
                      {event.recipient_role} - {event.status} via {event.channel}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted">No notification events recorded yet.</p>
              )}
            </div>
          </div>

          <div className="rounded-md border border-border bg-white p-4">
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
            </div>
          </div>

          {currentUser?.permissions.includes("tenant:admin") ? (
            <div className="rounded-md border border-border bg-white p-4">
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
            </div>
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
            <button className="rounded-md border border-border px-3 py-2 text-sm" type="button">
              Demo vendor session
            </button>
            <p className="mt-3 text-xs text-muted">{vendorAccess?.email ?? "vendor@example.com"}</p>
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
                <div className="px-4 py-6 text-sm text-muted">No vendor-visible invoices.</div>
              )}
            </div>
          </div>

          <div className="space-y-5">
            <div className="rounded-md border border-border p-4">
              <div className="mb-3 flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-[hsl(var(--accent))]" />
                <h3 className="text-base font-semibold">Vendor Message</h3>
              </div>
              <textarea
                className="min-h-24 w-full resize-none rounded-md border border-border p-3 text-sm"
                defaultValue="Please confirm the expected payment date."
              />
              <button className="mt-3 rounded-md bg-black px-3 py-2 text-sm text-white" type="button">
                Submit
              </button>
            </div>
            <div className="rounded-md border border-border p-4">
              <h3 className="text-base font-semibold">Status Chat</h3>
              <div className="mt-3 rounded-md border border-border px-3 py-2 text-sm text-muted">
                What is the payment status?
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
