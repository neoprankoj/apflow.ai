import { AlertTriangle, CheckCircle2, Info, MinusCircle } from "lucide-react";
import { cn } from "../../lib/utils";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const normalized = normalize(status);
  const tone = toneFor(normalized);
  const Icon = iconFor(tone);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium",
        tone === "success" && "border-green-200 bg-green-50 text-success",
        tone === "warning" && "border-amber-200 bg-amber-50 text-warning",
        tone === "danger" && "border-red-200 bg-red-50 text-danger",
        tone === "info" && "border-cyan-200 bg-cyan-50 text-info",
        tone === "neutral" && "border-border bg-slate-50 text-muted",
        className
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {humanize(normalized)}
    </span>
  );
}

function toneFor(status: string): Tone {
  if (["approved", "approval_ready", "auto_approved", "clear", "completed", "exported", "erp_ready", "good", "paid", "pass", "ready"].includes(status)) {
    return "success";
  }
  if (
    ["blocked", "on_hold", "missing_po", "review_required", "warning", "pending", "high", "likely_duplicate", "duplicate", "partially_ready"].includes(
      status
    )
  ) {
    return "warning";
  }
  if (["critical", "rejected", "failed", "overdue", "danger", "fail", "not_ready"].includes(status)) {
    return "danger";
  }
  if (["active", "processing", "running", "info"].includes(status)) {
    return "info";
  }
  return "neutral";
}

function iconFor(tone: Tone) {
  if (tone === "success") return CheckCircle2;
  if (tone === "warning" || tone === "danger") return AlertTriangle;
  if (tone === "info") return Info;
  return MinusCircle;
}

function normalize(value: string) {
  return value.trim().toLowerCase().replaceAll(" ", "_");
}

function humanize(value: string) {
  return value.replaceAll("_", " ");
}
