"use client";

import { BarChart3, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import {
  AccuracyAnalyticsResponse,
  AnalyticsBreakdownItem,
  AnalyticsExceptionItem,
  AnalyticsMetric,
  getAccuracyAnalytics
} from "./frontend-api";

export function AnalyticsDashboardPanel({
  accessToken,
  apiBaseUrl,
  tenantId
}: {
  accessToken: string | null;
  apiBaseUrl: string | null;
  tenantId: string | null;
}) {
  const [analytics, setAnalytics] = useState<AccuracyAnalyticsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setIsLoading(true);
    setError(null);
    try {
      setAnalytics(await getAccuracyAnalytics(apiBaseUrl, accessToken, tenantId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Accuracy analytics could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, apiBaseUrl, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const summaryCards = useMemo(() => {
    const metric = (group: AnalyticsMetric[], key: string) => group.find((item) => item.key === key);
    return [
      metric(analytics?.invoice_volume ?? [], "total_invoices"),
      metric(analytics?.ocr_accuracy ?? [], "review_required_rate"),
      metric(analytics?.exception_breakdown.map(exceptionToMetric) ?? [], "blocked_invoices"),
      metric(analytics?.erp_export_health ?? [], "mock_export_success"),
      metric(analytics?.vendor_self_service ?? [], "chatbot_answered"),
      metric(analytics?.notification_health ?? [], "notification_deliveries")
    ].filter(Boolean) as AnalyticsMetric[];
  }, [analytics]);

  return (
    <section className="scroll-mt-6 space-y-4" id="accuracy-analytics">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Accuracy & Exceptions</h2>
          <p className="mt-1 text-sm text-muted">
            Operational visibility for invoice throughput, review effort, blockers, exports, payments, vendor self-service, and notifications.
          </p>
        </div>
        <Button disabled={!tenantId || isLoading} onClick={() => void load()} variant="secondary">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}

      {isLoading && !analytics ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((item) => <LoadingSkeleton className="h-28 w-full" key={item} />)}
        </div>
      ) : analytics ? (
        <>
          {summaryCards.length ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {summaryCards.map((metric) => <MetricCard key={metric.key} metric={metric} />)}
            </div>
          ) : (
            <EmptyState
              description="Process invoices, run payment sync, vendor access, and notifications to populate metrics."
              title="No analytics yet"
            />
          )}

          <div className="grid gap-4 xl:grid-cols-2">
            <MetricSection items={analytics.ocr_accuracy} title="OCR & Review Health" />
            <MetricSection items={analytics.approval_health} title="Approval Health" />
            <ExceptionSection items={analytics.exception_breakdown} title="Exception Breakdown" />
            <MetricSection items={analytics.erp_export_health} title="ERP Export Health" />
            <BreakdownSection items={analytics.payment_status_health} title="Payment Status" />
            <MetricSection items={analytics.vendor_self_service} title="Vendor Self-Service" />
            <MetricSection items={analytics.notification_health} title="Notification Delivery" />
            <Recommendations items={analytics.recommendations} />
          </div>
        </>
      ) : (
        <EmptyState
          description="Sign in to load tenant-scoped accuracy and exception analytics."
          title="Analytics not loaded"
        />
      )}
    </section>
  );
}

function MetricCard({ metric }: { metric: AnalyticsMetric }) {
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm text-muted">{metric.label}</p>
          <StatusBadge status={metric.status} />
        </div>
        <p className="text-3xl font-semibold">
          {formatValue(metric.value)}
          {metric.unit ? <span className="text-base text-muted"> {metric.unit}</span> : null}
        </p>
        {metric.description ? <p className="text-xs text-muted">{metric.description}</p> : null}
      </CardContent>
    </Card>
  );
}

function MetricSection({ items, title }: { items: AnalyticsMetric[]; title: string }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold">{title}</h3>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length ? items.map((item) => (
          <div className="flex items-start justify-between gap-4 rounded-md border border-border p-3" key={item.key}>
            <div>
              <p className="font-medium">{item.label}</p>
              {item.description ? <p className="mt-1 text-sm text-muted">{item.description}</p> : null}
            </div>
            <div className="text-right">
              <StatusBadge status={item.status} />
              <p className="mt-2 font-semibold">{formatValue(item.value)}{item.unit ? ` ${item.unit}` : ""}</p>
            </div>
          </div>
        )) : <EmptyState title="No data yet" description="This section will populate as APFlow records activity." />}
      </CardContent>
    </Card>
  );
}

function ExceptionSection({ items, title }: { items: AnalyticsExceptionItem[]; title: string }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold">{title}</h3>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length ? items.map((item) => (
          <div className="rounded-md border border-border p-3" key={item.key}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-medium">{item.label}</p>
                {item.next_step ? <p className="mt-1 text-sm text-muted">Next: {item.next_step}</p> : null}
              </div>
              <div className="text-right">
                <StatusBadge status={item.severity} />
                <p className="mt-2 font-semibold">{item.count}</p>
              </div>
            </div>
          </div>
        )) : <EmptyState title="No exceptions recorded" description="Blockers, OCR errors, duplicate flags, and missing PO issues will appear here." />}
      </CardContent>
    </Card>
  );
}

function BreakdownSection({ items, title }: { items: AnalyticsBreakdownItem[]; title: string }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold">{title}</h3>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length ? items.map((item) => (
          <div className="flex items-center justify-between rounded-md border border-border p-3" key={item.key}>
            <div>
              <p className="font-medium">{item.label}</p>
              <p className="text-sm text-muted">{item.percentage ?? 0}% of payment statuses</p>
            </div>
            <p className="text-xl font-semibold">{item.count}</p>
          </div>
        )) : <EmptyState title="No payment status data" description="Run mock payment sync or update a payment status to populate this section." />}
      </CardContent>
    </Card>
  );
}

function Recommendations({ items }: { items: string[] }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-primary" />
          <h3 className="text-base font-semibold">Recommended Next Actions</h3>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3">
          {items.map((item) => (
            <li className="rounded-md border border-border p-3 text-sm" key={item}>{item}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function exceptionToMetric(item: AnalyticsExceptionItem): AnalyticsMetric {
  return {
    key: item.key,
    label: item.label,
    value: item.count,
    status: item.severity,
    description: item.next_step
  };
}

function formatValue(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
