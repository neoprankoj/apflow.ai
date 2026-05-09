"use client";

import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { apiFetch } from "./frontend-api";

type Props = {
  accessToken: string | null;
  apiBaseUrl: string;
  canReset: boolean;
  onResetComplete?: () => void;
};

export function DemoResetButton({ accessToken, apiBaseUrl, canReset, onResetComplete }: Props) {
  const [status, setStatus] = useState<"idle" | "running" | "done" | "failed">("idle");
  const [message, setMessage] = useState<string>("Staging-only reset is disabled unless explicitly enabled.");

  async function resetDemo() {
    if (!canReset) return;
    setStatus("running");
    setMessage("Resetting demo data...");
    try {
      const body = await apiFetch<{ invoice_number?: string; workflow_status: string }>(apiBaseUrl, "/admin/demo/reset", {
        method: "POST",
        token: accessToken,
        action: "Demo reset"
      });
      setStatus("done");
      setMessage(`${body.invoice_number ?? "Demo invoice"} is ${body.workflow_status.replaceAll("_", " ")}.`);
      onResetComplete?.();
    } catch (error) {
      setStatus("failed");
      setMessage(error instanceof Error ? error.message : "Demo reset failed because the API is unavailable.");
    }
  }

  return (
    <div className="rounded-md border border-border bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Demo Reset</h2>
          <p className="mt-1 text-sm text-muted">{message}</p>
        </div>
        <button
          className="rounded-md border border-border px-3 py-2 text-sm disabled:text-muted"
          disabled={!canReset || !accessToken || status === "running"}
          onClick={resetDemo}
          type="button"
        >
          <RotateCcw className="mr-2 inline h-4 w-4" />
          {status === "running" ? "Resetting" : "Reset"}
        </button>
      </div>
    </div>
  );
}
