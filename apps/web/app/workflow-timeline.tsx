import { AlertTriangle, CheckCircle2, Clock3, Loader2 } from "lucide-react";

export type TimelineStageStatus = "pending" | "active" | "completed" | "warning" | "failed";

export type TimelineStage = {
  id: string;
  label: string;
  status: TimelineStageStatus;
  timestamp?: string;
  summary: string;
  warning?: string;
};

export function WorkflowTimeline({ stages }: { stages: TimelineStage[] }) {
  if (!stages.length) {
    return (
      <div className="rounded-md border border-border px-4 py-5 text-sm text-muted">
        No workflow activity yet.
      </div>
    );
  }

  return (
    <div className="divide-y divide-border rounded-md border border-border">
      {stages.map((stage) => {
        const Icon = iconFor(stage.status);
        return (
          <div className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-[28px_170px_1fr_150px]" key={stage.id}>
            <Icon className={`mt-0.5 h-4 w-4 ${colorFor(stage.status)}`} />
            <div>
              <p className="font-medium">{stage.label}</p>
              <p className="text-xs text-muted">{stage.status.replaceAll("_", " ")}</p>
            </div>
            <div>
              <p>{stage.summary}</p>
              {stage.warning ? <p className="mt-1 text-xs text-amber-700">{stage.warning}</p> : null}
            </div>
            <span className="text-xs text-muted">{stage.timestamp ? formatTime(stage.timestamp) : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

function iconFor(status: TimelineStageStatus) {
  if (status === "completed") return CheckCircle2;
  if (status === "active") return Loader2;
  if (status === "warning" || status === "failed") return AlertTriangle;
  return Clock3;
}

function colorFor(status: TimelineStageStatus) {
  if (status === "completed") return "text-green-700";
  if (status === "active") return "animate-spin text-[hsl(var(--accent))]";
  if (status === "warning") return "text-amber-700";
  if (status === "failed") return "text-red-700";
  return "text-muted";
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}
