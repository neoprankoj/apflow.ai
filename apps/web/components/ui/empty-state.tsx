import { type LucideIcon, Inbox } from "lucide-react";
import { cn } from "../../lib/utils";

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  className
}: {
  title: string;
  description: string;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-lg border border-dashed border-border px-6 py-10 text-center", className)}>
      <span className="mb-3 rounded-full bg-slate-100 p-3 text-muted">
        <Icon className="h-5 w-5" />
      </span>
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-muted">{description}</p>
    </div>
  );
}
