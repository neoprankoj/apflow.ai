import { Search } from "lucide-react";
import { type ReactNode } from "react";

export function TopHeader({
  title,
  subtitle,
  breadcrumbs,
  actions
}: {
  title: string;
  subtitle?: string;
  breadcrumbs?: string[];
  actions?: ReactNode;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-screen-xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          {breadcrumbs?.length ? (
            <p className="mb-1 text-xs font-medium uppercase tracking-[0.08em] text-muted">{breadcrumbs.join(" / ")}</p>
          ) : null}
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-muted">{subtitle}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="hidden items-center gap-2 rounded-md border border-border bg-white px-3 py-2 text-sm text-muted sm:flex">
            <Search className="h-4 w-4" />
            <span>Search invoices, vendors, POs</span>
          </div>
          {actions}
        </div>
      </div>
    </header>
  );
}
