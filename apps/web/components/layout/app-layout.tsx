"use client";

import { type ReactNode } from "react";
import { Sidebar, type SidebarItem } from "./sidebar";
import { TopHeader } from "./top-header";

export function AppLayout({
  navItems,
  activeSection,
  onSectionChange,
  title,
  subtitle,
  breadcrumbs,
  actions,
  children,
  aside
}: {
  navItems: SidebarItem[];
  activeSection: string;
  onSectionChange: (id: string) => void;
  title: string;
  subtitle?: string;
  breadcrumbs?: string[];
  actions?: ReactNode;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="lg:flex">
        <Sidebar activeItem={activeSection} items={navItems} onSelect={onSectionChange} />
        <div className="min-w-0 flex-1">
          <TopHeader actions={actions} breadcrumbs={breadcrumbs} subtitle={subtitle} title={title} />
          <div className="mx-auto grid max-w-screen-xl gap-6 px-4 py-6 sm:px-6 xl:grid-cols-[minmax(0,1fr)_320px]">
            <section className="min-w-0 space-y-6">{children}</section>
            {aside ? <aside className="space-y-6">{aside}</aside> : null}
          </div>
        </div>
      </div>
    </main>
  );
}
