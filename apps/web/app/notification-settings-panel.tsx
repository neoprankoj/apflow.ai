"use client";

import { Bell, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import {
  getNotificationSummary,
  getNotificationReadiness,
  listNotificationDeliveries,
  listNotificationProviders,
  NotificationDeliveryRead,
  NotificationProviderRead,
  NotificationReadinessResponse,
  NotificationSummary,
  sendTestNotification
} from "./frontend-api";

const channels = ["mock", "email", "slack", "teams"];
const emailReadinessChecklist = [
  "Domain selected",
  "Sender email chosen",
  "SPF planned",
  "DKIM planned",
  "DMARC planned",
  "SMTP credentials stored server-side only",
  "Test recipient approved"
];

export function NotificationSettingsPanel({
  accessToken,
  apiBaseUrl,
  canSendNotifications,
  tenantId
}: {
  accessToken: string | null;
  apiBaseUrl: string | null;
  canSendNotifications: boolean;
  tenantId: string | null;
}) {
  const [providers, setProviders] = useState<NotificationProviderRead[]>([]);
  const [readiness, setReadiness] = useState<NotificationReadinessResponse | null>(null);
  const [deliveries, setDeliveries] = useState<NotificationDeliveryRead[]>([]);
  const [summary, setSummary] = useState<NotificationSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [channel, setChannel] = useState("mock");
  const [recipientLabel, setRecipientLabel] = useState("APFlow demo operator");
  const [recipientAddress, setRecipientAddress] = useState("operator@example.local");
  const [subject, setSubject] = useState("APFlow notification test");
  const [body, setBody] = useState("This is a safe mock notification test. No external message is sent.");

  const load = useCallback(async () => {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [loadedProviders, loadedReadiness, loadedDeliveries, loadedSummary] = await Promise.all([
        listNotificationProviders(apiBaseUrl, accessToken, tenantId),
        getNotificationReadiness(apiBaseUrl, accessToken, tenantId),
        listNotificationDeliveries(apiBaseUrl, accessToken, tenantId),
        getNotificationSummary(apiBaseUrl, accessToken, tenantId)
      ]);
      setProviders(loadedProviders);
      setReadiness(loadedReadiness);
      setDeliveries(loadedDeliveries.slice(-8).reverse());
      setSummary(loadedSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Notification settings could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, apiBaseUrl, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const summaryCards = useMemo(
    () => [
      { label: "Sent", value: summary?.sent ?? 0, status: "sent" },
      { label: "Failed", value: summary?.failed ?? 0, status: "failed" },
      { label: "Disabled", value: summary?.disabled ?? 0, status: "disabled" },
      { label: "Queued", value: summary?.queued ?? 0, status: "queued" }
    ],
    [summary]
  );

  async function handleSendTest() {
    if (!apiBaseUrl || !accessToken || !tenantId) return;
    setIsSending(true);
    setError(null);
    setMessage(null);
    try {
      const delivery = await sendTestNotification(apiBaseUrl, accessToken, {
        tenant_id: tenantId,
        channel,
        recipient_label: recipientLabel || null,
        recipient_address: recipientAddress || null,
        subject: subject || null,
        message: body || null
      });
      setMessage(
        delivery.status === "sent"
          ? "Mock notification recorded inside APFlow only. No external message was sent."
          : delivery.reason ?? "Provider is not configured, so no external message was sent."
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Notification test failed.");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className="scroll-mt-6 space-y-4" id="notification-settings">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Notification Settings</h2>
          <p className="mt-1 text-sm text-muted">
            Mock notifications are recorded inside APFlow only. Email, Slack, and Teams providers are placeholders and do not send externally.
          </p>
        </div>
        <Button disabled={!tenantId || isLoading} onClick={() => void load()} variant="secondary">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}
      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{message}</div> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map((item) => (
          <Card key={item.label}>
            <CardContent className="space-y-2">
              <StatusBadge status={item.status} />
              <p className="text-2xl font-semibold">{item.value}</p>
              <p className="text-sm text-muted">{item.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <h3 className="text-base font-semibold">Real Provider Readiness</h3>
          </div>
          <p className="mt-1 text-sm text-muted">
            Mock notifications are safe for demos. Real external delivery remains disabled until provider secrets and sender-domain setup are reviewed.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {[0, 1, 2, 3].map((item) => <LoadingSkeleton className="h-28 w-full" key={item} />)}
            </div>
          ) : readiness ? (
            <>
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <StatusBadge status={readiness.real_delivery_enabled ? "enabled" : "disabled"} />
                <span className="text-muted">Real delivery enabled: {readiness.real_delivery_enabled ? "Yes" : "No"}</span>
                <span className="text-muted">Default provider: {label(readiness.default_provider)}</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {readiness.providers.map((provider) => (
                  <div className="rounded-md border border-border p-4" key={provider.provider}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{provider.label}</p>
                        <p className="mt-1 text-sm text-muted">{provider.notes[0] ?? "Provider readiness is safe to view."}</p>
                      </div>
                      <StatusBadge status={provider.status} />
                    </div>
                    {provider.missing_requirements.length ? (
                      <ul className="mt-3 space-y-1 text-xs text-muted">
                        {provider.missing_requirements.slice(0, 3).map((requirement) => (
                          <li key={requirement}>{requirement}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <div className="rounded-md border border-border p-4">
                  <p className="text-sm font-medium">Email Setup Checklist</p>
                  <ul className="mt-2 grid gap-1 text-sm text-muted sm:grid-cols-2">
                    {emailReadinessChecklist.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
                <div className="rounded-md border border-border p-4">
                  <p className="text-sm font-medium">Domain and Delivery Notes</p>
                  <ul className="mt-2 space-y-1 text-sm text-muted">
                    {readiness.domain_requirements.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
              </div>
            </>
          ) : (
            <EmptyState title="No readiness loaded" description="Sign in to load safe real provider readiness." />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card>
          <CardHeader>
            <h3 className="text-base font-semibold">Notification Providers</h3>
            <p className="mt-1 text-sm text-muted">Provider readiness is safe to view and never includes API keys, webhook URLs, or secrets.</p>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-3">
                {[0, 1, 2, 3].map((item) => <LoadingSkeleton className="h-16 w-full" key={item} />)}
              </div>
            ) : providers.length ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {providers.map((provider) => (
                  <div className="rounded-md border border-border p-4" key={provider.channel}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{label(provider.channel)}</p>
                        <p className="mt-1 text-sm text-muted">{provider.safe_message}</p>
                      </div>
                      <StatusBadge status={provider.enabled && provider.configured ? "configured" : "not_configured"} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No providers loaded" description="Sign in to load notification provider readiness." />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h3 className="text-base font-semibold">Test Notification</h3>
            <p className="mt-1 text-sm text-muted">Mock tests are recorded only in APFlow. Placeholder channels return a safe not-configured result.</p>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="block text-sm font-medium">
              Channel
              <select className="mt-1 w-full rounded-md border border-border px-3 py-2" onChange={(event) => setChannel(event.target.value)} value={channel}>
                {channels.map((item) => <option key={item} value={item}>{label(item)}</option>)}
              </select>
            </label>
            <label className="block text-sm font-medium">
              Recipient label
              <input className="mt-1 w-full rounded-md border border-border px-3 py-2" onChange={(event) => setRecipientLabel(event.target.value)} value={recipientLabel} />
            </label>
            <label className="block text-sm font-medium">
              Recipient address
              <input className="mt-1 w-full rounded-md border border-border px-3 py-2" onChange={(event) => setRecipientAddress(event.target.value)} value={recipientAddress} />
            </label>
            <label className="block text-sm font-medium">
              Subject
              <input className="mt-1 w-full rounded-md border border-border px-3 py-2" onChange={(event) => setSubject(event.target.value)} value={subject} />
            </label>
            <label className="block text-sm font-medium">
              Message
              <textarea className="mt-1 min-h-24 w-full rounded-md border border-border px-3 py-2" onChange={(event) => setBody(event.target.value)} value={body} />
            </label>
            <Button disabled={!canSendNotifications || isSending || !tenantId} onClick={() => void handleSendTest()} variant="primary">
              <Send className="h-4 w-4" />
              Send Test
            </Button>
            {!canSendNotifications ? <p className="text-sm text-muted">You do not have permission to send notification tests.</p> : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-primary" />
            <h3 className="text-base font-semibold">Delivery History</h3>
          </div>
          <p className="mt-1 text-sm text-muted">Latest notification delivery attempts. Body previews are truncated and addresses are redacted.</p>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3 p-5">
              {[0, 1, 2].map((item) => <LoadingSkeleton className="h-14 w-full" key={item} />)}
            </div>
          ) : deliveries.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-border bg-slate-50 text-xs uppercase text-muted">
                  <tr>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Channel</th>
                    <th className="px-4 py-3">Event</th>
                    <th className="px-4 py-3">Recipient</th>
                    <th className="px-4 py-3">Preview</th>
                    <th className="px-4 py-3">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {deliveries.map((delivery) => (
                    <tr className="hover:bg-slate-50" key={delivery.id}>
                      <td className="px-4 py-3"><StatusBadge status={delivery.status} /></td>
                      <td className="px-4 py-3">{label(delivery.channel)}</td>
                      <td className="px-4 py-3">{label(delivery.event_type)}</td>
                      <td className="px-4 py-3">
                        <p>{delivery.recipient_label}</p>
                        <p className="text-xs text-muted">{delivery.recipient_address_redacted ?? "No address stored"}</p>
                      </td>
                      <td className="max-w-md px-4 py-3 text-muted">{delivery.body_preview ?? delivery.reason ?? "No preview"}</td>
                      <td className="px-4 py-3 text-muted">{formatDate(delivery.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-5">
              <EmptyState title="No notification deliveries yet" description="Send a mock test notification to record the first delivery attempt. No external channel is contacted." />
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatDate(value?: string | null) {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
