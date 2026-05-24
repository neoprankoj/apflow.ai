"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { KeyRound, RefreshCw, RotateCw, ShieldCheck } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import {
  ApiRequestError,
  createVendorAccess,
  listVendorAccesses,
  revokeVendorAccess,
  rotateVendorAccess,
  type VendorAccessCreatedResponse,
  type VendorAccessRead,
  type VendorAccessRotateResponse
} from "./frontend-api";

type VendorAccessAdminProps = {
  accessToken: string | null;
  apiBaseUrl: string | null;
  canManageVendorAccess: boolean;
  tenantId: string | null;
};

export function VendorAccessAdmin({
  accessToken,
  apiBaseUrl,
  canManageVendorAccess,
  tenantId
}: VendorAccessAdminProps) {
  const [records, setRecords] = useState<VendorAccessRead[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [oneTimeToken, setOneTimeToken] = useState<VendorAccessCreatedResponse | VendorAccessRotateResponse | null>(null);
  const [email, setEmail] = useState("vendor@example.com");
  const [vendorName, setVendorName] = useState("Northstar Components");
  const [label, setLabel] = useState("Supplier self-service access");
  const [ttlDays, setTtlDays] = useState(30);

  const canLoad = Boolean(accessToken && apiBaseUrl && tenantId);

  const loadRecords = useCallback(async () => {
    if (!accessToken || !apiBaseUrl || !tenantId) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await listVendorAccesses(apiBaseUrl, accessToken, tenantId);
      setRecords(result);
    } catch (err) {
      setError(readError(err, "Vendor access records could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, apiBaseUrl, tenantId]);

  useEffect(() => {
    if (canLoad && canManageVendorAccess) {
      void loadRecords();
    }
  }, [canLoad, canManageVendorAccess, loadRecords]);

  const activeCount = useMemo(() => records.filter((record) => record.status === "active").length, [records]);

  async function handleCreate() {
    if (!accessToken || !apiBaseUrl || !tenantId) return;
    setIsSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const created = await createVendorAccess(apiBaseUrl, accessToken, {
        tenant_id: tenantId,
        email,
        vendor_name: vendorName,
        label,
        ttl_days: ttlDays
      });
      setOneTimeToken(created);
      setMessage("Vendor access created. Copy the token now; it will not be shown again.");
      await loadRecords();
    } catch (err) {
      setError(readError(err, "Vendor access could not be created."));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRevoke(accessId: string) {
    if (!accessToken || !apiBaseUrl || !tenantId) return;
    if (!window.confirm("Revoke this vendor access token? The supplier will no longer be able to use it.")) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await revokeVendorAccess(apiBaseUrl, accessToken, tenantId, accessId);
      setMessage(result.message);
      await loadRecords();
    } catch (err) {
      setError(readError(err, "Vendor access could not be revoked."));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRotate(accessId: string) {
    if (!accessToken || !apiBaseUrl || !tenantId) return;
    if (!window.confirm("Rotate this vendor access token? The old token will be revoked and a new one will be shown once.")) return;
    setIsSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const rotated = await rotateVendorAccess(apiBaseUrl, accessToken, tenantId, accessId);
      setOneTimeToken(rotated);
      setMessage("Vendor access rotated. Copy the replacement token now; it will not be shown again.");
      await loadRecords();
    } catch (err) {
      setError(readError(err, "Vendor access could not be rotated."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="scroll-mt-6 space-y-3" id="vendor-access-admin">
      <div>
        <h2 className="text-lg font-semibold">Vendor Access Management</h2>
        <p className="text-sm text-muted">
          Create secure vendor self-service tokens for supplier invoice and payment status visibility. Tokens are shown only once.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <h3 className="text-base font-semibold">Production Access Foundation</h3>
            </div>
            <p className="mt-1 text-sm text-muted">
              Vendor tokens are hashed, expire, can be revoked or rotated, and can only see vendor-safe invoice/payment data.
            </p>
          </div>
          <Button disabled={!canLoad || isLoading || !canManageVendorAccess} onClick={() => void loadRecords()} variant="secondary">
            <RefreshCw className="h-4 w-4" />
            Reload
          </Button>
        </CardHeader>
        <CardContent className="space-y-5">
          {!canManageVendorAccess ? (
            <EmptyState
              description="You can view the dashboard, but you do not have permission to create, revoke, or rotate vendor access."
              title="Vendor access is admin-controlled"
            />
          ) : null}

          {canManageVendorAccess ? (
            <div className="grid gap-4 rounded-md border border-border p-4 lg:grid-cols-[1fr_1fr_1fr_120px_auto]">
              <Field label="Supplier email">
                <input className="w-full rounded-md border border-border px-3 py-2 text-sm" onChange={(event) => setEmail(event.target.value)} value={email} />
              </Field>
              <Field label="Supplier name">
                <input className="w-full rounded-md border border-border px-3 py-2 text-sm" onChange={(event) => setVendorName(event.target.value)} value={vendorName} />
              </Field>
              <Field label="Label">
                <input className="w-full rounded-md border border-border px-3 py-2 text-sm" onChange={(event) => setLabel(event.target.value)} value={label} />
              </Field>
              <Field label="TTL days">
                <input
                  className="w-full rounded-md border border-border px-3 py-2 text-sm"
                  min={1}
                  max={365}
                  onChange={(event) => setTtlDays(Number(event.target.value))}
                  type="number"
                  value={ttlDays}
                />
              </Field>
              <div className="flex items-end">
                <Button disabled={!canLoad || isSubmitting || !email.trim()} onClick={() => void handleCreate()} variant="primary">
                  <KeyRound className="h-4 w-4" />
                  Create Access
                </Button>
              </div>
            </div>
          ) : null}

          {oneTimeToken ? (
            <div className="rounded-md border border-warning/40 bg-warning/5 p-4">
              <p className="text-sm font-semibold text-main">Copy this token now. It will not be shown again.</p>
              <textarea className="mt-3 min-h-20 w-full rounded-md border border-border p-3 font-mono text-xs" readOnly value={oneTimeToken.access_token} />
              {oneTimeToken.access_url ? (
                <p className="mt-2 break-all text-xs text-muted">Access URL: {oneTimeToken.access_url}</p>
              ) : (
                <p className="mt-2 text-xs text-muted">No public vendor URL is configured yet. Use the token through the vendor API/session flow.</p>
              )}
            </div>
          ) : null}

          {message ? <p className="rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm text-success">{message}</p> : null}
          {error ? <p className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p> : null}

          <div className="grid gap-3 sm:grid-cols-3">
            <MiniStat label="Active access" value={activeCount.toString()} />
            <MiniStat label="Total records" value={records.length.toString()} />
            <MiniStat label="Priority writes" value="Disabled" />
          </div>

          {isLoading ? (
            <div className="space-y-2">
              <LoadingSkeleton className="h-10" />
              <LoadingSkeleton className="h-10" />
              <LoadingSkeleton className="h-10" />
              <LoadingSkeleton className="h-10" />
            </div>
          ) : records.length ? (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-muted">
                  <tr>
                    {["status", "supplier", "email", "token", "expires", "last used", "actions"].map((heading) => (
                      <th className="px-3 py-2" key={heading}>{heading}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {records.map((record) => (
                    <tr className="hover:bg-slate-50" key={record.id}>
                      <td className="px-3 py-3 align-top"><StatusBadge status={record.status} /></td>
                      <td className="px-3 py-3 align-top">
                        <p className="font-medium">{record.vendor_name ?? "Supplier"}</p>
                        <p className="text-xs text-muted">{record.label ?? "Vendor portal access"}</p>
                      </td>
                      <td className="px-3 py-3 align-top">{record.email}</td>
                      <td className="px-3 py-3 align-top font-mono text-xs">{record.token_prefix ?? "-"}</td>
                      <td className="px-3 py-3 align-top">{formatDate(record.expires_at)}</td>
                      <td className="px-3 py-3 align-top">{formatDate(record.last_used_at)}</td>
                      <td className="px-3 py-3 align-top">
                        <div className="flex flex-wrap gap-2">
                          <Button disabled={isSubmitting || record.status !== "active"} onClick={() => void handleRotate(record.id)} variant="secondary">
                            <RotateCw className="h-4 w-4" />
                            Rotate
                          </Button>
                          <Button disabled={isSubmitting || record.status !== "active"} onClick={() => void handleRevoke(record.id)} variant="danger">
                            Revoke
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              description="Create vendor access after a supplier has invoices in APFlow. Imported or processed invoices remain tenant-scoped and vendor-filtered."
              title="No vendor access records"
            />
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function Field({ children, label }: { children: ReactNode; label: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-main">{label}</span>
      {children}
    </label>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs uppercase text-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function readError(error: unknown, fallback: string) {
  if (error instanceof ApiRequestError) return error.detail ?? error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}
