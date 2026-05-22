"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { getProductReadiness, type ProductReadinessCheck, type ProductReadinessResponse } from "./frontend-api";

type ProductReadinessPanelProps = {
  accessToken: string | null;
  apiBaseUrl: string | null;
  canAdmin: boolean;
};

const GROUPS = [
  { key: "demo", label: "Demo" },
  { key: "operations", label: "Operations" },
  { key: "security", label: "Security" },
  { key: "integrations", label: "Integrations" },
  { key: "pilot", label: "Pilot blockers" },
  { key: "production", label: "Production blockers" },
  { key: "commercial", label: "Commercial readiness" }
];

export function ProductReadinessPanel({ accessToken, apiBaseUrl, canAdmin }: ProductReadinessPanelProps) {
  const [readiness, setReadiness] = useState<ProductReadinessResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReadiness = useCallback(async () => {
    if (!apiBaseUrl || !accessToken || !canAdmin) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await getProductReadiness(apiBaseUrl, accessToken);
      setReadiness(result);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Product readiness failed to load.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, apiBaseUrl, canAdmin]);

  useEffect(() => {
    void loadReadiness();
  }, [loadReadiness]);

  const groupedChecks = useMemo(() => groupChecks(readiness?.checks ?? []), [readiness]);

  return (
    <section className="scroll-mt-6 space-y-3" id="product-readiness">
      <div>
        <h2 className="text-lg font-semibold">Product Readiness Gate</h2>
        <p className="text-sm text-muted">
          Shows what APFlow is safe to claim today. This does not enable production or change runtime behavior.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-base font-semibold">Demo / Pilot / Production Readiness</h3>
            <p className="mt-1 max-w-2xl text-sm text-muted">
              Use this before customer conversations to separate controlled demo readiness from pilot and production blockers.
            </p>
          </div>
          <Button disabled={!canAdmin || isLoading || !accessToken || !apiBaseUrl} onClick={() => void loadReadiness()} variant="secondary">
            {isLoading ? "Loading..." : "Reload readiness"}
          </Button>
        </CardHeader>

        <CardContent className="space-y-5">
          {!canAdmin ? (
            <EmptyState
              description="Only tenant admins can view product readiness because it exposes operational posture."
              title="Readiness is admin-only"
            />
          ) : isLoading && !readiness ? (
            <div className="grid gap-4 lg:grid-cols-3">
              {[0, 1, 2].map((item) => (
                <LoadingSkeleton className="h-32 w-full" key={item} />
              ))}
            </div>
          ) : error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
          ) : readiness ? (
            <>
              <div className="grid gap-4 lg:grid-cols-3">
                <ReadinessLevelCard label="Demo Ready" level={readiness.demo_ready} />
                <ReadinessLevelCard label="Pilot Ready" level={readiness.pilot_ready} />
                <ReadinessLevelCard label="Production Ready" level={readiness.production_ready} />
              </div>

              <div className="rounded-md border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-900">
                {readiness.message}
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                {GROUPS.map((group) => (
                  <CheckGroup checks={groupedChecks[group.key] ?? []} key={group.key} title={group.label} />
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              description="Sign in as an owner/admin and reload readiness to see Demo, Pilot, and Production status."
              title="Readiness not loaded"
            />
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function ReadinessLevelCard({ label, level }: { label: string; level: ProductReadinessResponse["demo_ready"] }) {
  return (
    <Card className="shadow-none">
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <h4 className="font-semibold">{label}</h4>
          <StatusBadge status={level.status} />
        </div>
        <p className="text-sm text-muted">{level.summary}</p>
        {level.blockers.length ? (
          <p className="text-xs text-danger">{level.blockers.length} blocker{level.blockers.length === 1 ? "" : "s"}</p>
        ) : level.warnings.length ? (
          <p className="text-xs text-warning">{level.warnings.length} warning{level.warnings.length === 1 ? "" : "s"}</p>
        ) : (
          <p className="text-xs text-success">No blockers</p>
        )}
      </CardContent>
    </Card>
  );
}

function CheckGroup({ checks, title }: { checks: ProductReadinessCheck[]; title: string }) {
  return (
    <div className="rounded-md border border-border bg-surface">
      <div className="border-b border-border px-4 py-3">
        <h4 className="text-sm font-semibold">{title}</h4>
      </div>
      {checks.length ? (
        <div className="divide-y divide-border">
          {checks.map((check) => (
            <div className="space-y-2 px-4 py-3 text-sm" key={check.key}>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="font-medium">{check.label}</p>
                  <p className="mt-1 text-muted">{check.message}</p>
                </div>
                <StatusBadge status={check.status} />
              </div>
              {check.next_step ? <p className="text-xs text-muted">Next: {check.next_step}</p> : null}
              {check.safe_detail ? <p className="text-xs text-muted">Detail: {check.safe_detail}</p> : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="p-4">
          <EmptyState description="No checks are currently assigned to this category." title="No checks" />
        </div>
      )}
    </div>
  );
}

function groupChecks(checks: ProductReadinessCheck[]) {
  return checks.reduce<Record<string, ProductReadinessCheck[]>>((groups, check) => {
    const key = check.category || "operations";
    groups[key] = groups[key] ? [...groups[key], check] : [check];
    return groups;
  }, {});
}
