"use client";

import { CreditCard, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import {
  getUsageSummary,
  listUsagePlans,
  TenantUsageSummary,
  UsageMetricRead,
  UsagePlanRead
} from "./frontend-api";

export function UsageBillingPanel({
  accessToken,
  apiBaseUrl,
  tenantId
}: {
  accessToken: string | null;
  apiBaseUrl: string | null;
  tenantId: string | null;
}) {
  const [summary, setSummary] = useState<TenantUsageSummary | null>(null);
  const [plans, setPlans] = useState<UsagePlanRead[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [usage, availablePlans] = await Promise.all([
        getUsageSummary(apiBaseUrl, accessToken, tenantId),
        listUsagePlans(apiBaseUrl, accessToken, tenantId)
      ]);
      setSummary(usage);
      setPlans(availablePlans);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Usage summary could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, apiBaseUrl, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasUsage = useMemo(() => {
    if (!summary) return false;
    return Object.values(summary.usage_by_event_type).some((value) => value > 0);
  }, [summary]);

  return (
    <section className="scroll-mt-6 space-y-4" id="usage-plan">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Usage & Plan</h2>
          <p className="mt-1 text-sm text-muted">
            Usage metering is for visibility only. No real billing provider, checkout, card storage, or customer invoicing is connected yet.
          </p>
        </div>
        <Button disabled={!tenantId || isLoading} onClick={() => void load()} variant="secondary">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}

      {isLoading && !summary ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((item) => <LoadingSkeleton className="h-28 w-full" key={item} />)}
        </div>
      ) : summary ? (
        <>
          <Card>
            <CardContent className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-start gap-3">
                <div className="rounded-md bg-primary/10 p-2 text-primary">
                  <CreditCard className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-semibold">{summary.current_plan.label} plan</p>
                  <p className="mt-1 text-sm text-muted">{summary.current_plan.description}</p>
                  <p className="mt-2 text-xs text-muted">Limits are warn-only. APFlow will not block workflow activity in this PR.</p>
                </div>
              </div>
              <StatusBadge status={summary.current_plan.overage_policy} />
            </CardContent>
          </Card>

          {hasUsage ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {summary.limits.map((metric) => <UsageMetricCard key={metric.key} metric={metric} />)}
            </div>
          ) : (
            <EmptyState
              description="Upload/process invoices, run payment sync, create vendor access, ask the chatbot, or send mock notifications to populate usage."
              title="No metered usage yet"
            />
          )}

          <div className="grid gap-4 xl:grid-cols-2">
            <UsageBreakdown summary={summary} />
            <RecentUsageEvents summary={summary} />
            <PlanPreview plans={plans} />
            <Recommendations recommendations={summary.recommendations} warnings={summary.warnings} />
          </div>
        </>
      ) : (
        <EmptyState description="Sign in to load tenant-scoped usage and plan readiness." title="Usage not loaded" />
      )}
    </section>
  );
}

function UsageMetricCard({ metric }: { metric: UsageMetricRead }) {
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm text-muted">{metric.label}</p>
          <StatusBadge status={metric.status} />
        </div>
        <p className="text-3xl font-semibold">{metric.used}</p>
        <p className="text-xs text-muted">
          {metric.limit == null ? "Unlimited placeholder" : `${metric.percentage ?? 0}% of ${metric.limit} ${metric.unit}s`}
        </p>
        {metric.description ? <p className="text-xs text-muted">{metric.description}</p> : null}
      </CardContent>
    </Card>
  );
}

function UsageBreakdown({ summary }: { summary: TenantUsageSummary }) {
  const entries = Object.entries(summary.usage_by_category);
  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold">Usage Categories</h3>
      </CardHeader>
      <CardContent className="space-y-3">
        {entries.length ? entries.map(([category, count]) => (
          <div className="flex items-center justify-between rounded-md border border-border p-3" key={category}>
            <p className="font-medium capitalize">{category.replaceAll("_", " ")}</p>
            <p className="text-xl font-semibold">{count}</p>
          </div>
        )) : <EmptyState title="No categories yet" description="Metered activity will appear here by category." />}
      </CardContent>
    </Card>
  );
}

function RecentUsageEvents({ summary }: { summary: TenantUsageSummary }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold">Recent Usage Events</h3>
      </CardHeader>
      <CardContent className="space-y-3">
        {summary.recent_events.length ? summary.recent_events.map((event) => (
          <div className="rounded-md border border-border p-3" key={event.id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{event.event_type.replaceAll("_", " ")}</p>
                <p className="mt-1 text-xs text-muted">{event.source} · {new Date(event.occurred_at).toLocaleString()}</p>
              </div>
              <p className="font-semibold">{event.quantity}</p>
            </div>
          </div>
        )) : <EmptyState title="No usage events yet" description="Usage events are recorded as operators use APFlow." />}
      </CardContent>
    </Card>
  );
}

function PlanPreview({ plans }: { plans: UsagePlanRead[] }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold">Plan Placeholders</h3>
      </CardHeader>
      <CardContent className="space-y-3">
        {plans.map((plan) => (
          <div className="rounded-md border border-border p-3" key={plan.plan_key}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{plan.label}</p>
                <p className="mt-1 text-sm text-muted">{plan.description}</p>
              </div>
              {plan.is_current ? <StatusBadge status="active" /> : null}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function Recommendations({ recommendations, warnings }: { recommendations: string[]; warnings: string[] }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold">Billing Readiness Notes</h3>
      </CardHeader>
      <CardContent className="space-y-3">
        {warnings.map((warning) => (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" key={warning}>{warning}</div>
        ))}
        {recommendations.map((item) => (
          <div className="rounded-md border border-border p-3 text-sm" key={item}>{item}</div>
        ))}
      </CardContent>
    </Card>
  );
}
