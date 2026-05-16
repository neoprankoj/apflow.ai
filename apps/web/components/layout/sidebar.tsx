"use client";

import { ArrowRight } from "lucide-react";
import { cn } from "../../lib/utils";

export type SidebarItem = {
  id: string;
  label: string;
};

export function Sidebar({
  items,
  activeItem,
  onSelect
}: {
  items: SidebarItem[];
  activeItem: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="w-full shrink-0 border-b border-border bg-surface lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:border-b-0 lg:border-r">
      <div className="border-b border-border px-5 py-5">
        <p className="text-lg font-semibold">APFlow AI</p>
        <p className="mt-1 text-sm text-muted">Accounts payable operations</p>
      </div>
      <nav aria-label="Primary" className="flex gap-1 overflow-x-auto px-3 py-3 text-sm lg:block lg:space-y-1 lg:overflow-visible">
        {items.map((item) => (
          <a
            className={cn(
              "flex min-w-fit items-center justify-between rounded-md px-3 py-2.5 text-left transition-colors",
              activeItem === item.id ? "bg-blue-50 font-medium text-primary" : "text-foreground hover:bg-slate-50"
            )}
            href={`#${item.id}`}
            key={item.id}
            onClick={() => onSelect(item.id)}
          >
            {item.label}
            {activeItem === item.id ? <ArrowRight className="ml-3 h-4 w-4" /> : null}
          </a>
        ))}
      </nav>
    </aside>
  );
}
