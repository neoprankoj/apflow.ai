"use client";

import {
  CheckCircle2,
  ClipboardCheck,
  FilePlus2,
  History,
  type LucideIcon,
  ScanText,
  Send,
  ShieldCheck,
  SlidersHorizontal
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { StatusBadge } from "../components/ui/status-badge";

type StageStatus = "not started" | "ready" | "needs attention" | "complete";

type WorkflowGuideProps = {
  approvalReadyCount: number;
  auditEventCount: number;
  blockedCount: number;
  exportedCount: number;
  invoiceCount: number;
  isSignedIn: boolean;
  openReviewCount: number;
  pendingApprovalCount: number;
  priorityMappingConfigured?: boolean | null;
  priorityMode: string;
  workflowCount: number;
  onNavigate: (sectionId: string) => void;
  onDemoLogin: () => void;
};

export function APWorkflowGuide({
  approvalReadyCount,
  auditEventCount,
  blockedCount,
  exportedCount,
  invoiceCount,
  isSignedIn,
  openReviewCount,
  pendingApprovalCount,
  priorityMappingConfigured,
  priorityMode,
  workflowCount,
  onNavigate,
  onDemoLogin
}: WorkflowGuideProps) {
  const nextAction = getNextAction({
    approvalReadyCount,
    auditEventCount,
    blockedCount,
    exportedCount,
    invoiceCount,
    isSignedIn,
    openReviewCount,
    pendingApprovalCount,
    priorityMappingConfigured
  });
  const stages = [
    {
      id: "upload-invoice-top",
      icon: FilePlus2,
      name: "Upload",
      status: invoiceCount ? "complete" : isSignedIn ? "ready" : "not started",
      description: "Upload a supplier invoice PDF or image.",
      action: invoiceCount ? "Review captured invoices" : "Go to Upload Invoice"
    },
    {
      id: "ocr-review",
      icon: ScanText,
      name: "OCR",
      status: workflowCount || invoiceCount ? "complete" : invoiceCount ? "ready" : "not started",
      description: "Extract invoice fields using OCR.",
      action: "Open OCR Review"
    },
    {
      id: "ocr-review",
      icon: ClipboardCheck,
      name: "Review",
      status: openReviewCount ? "needs attention" : invoiceCount ? "complete" : "not started",
      description: "Correct low-confidence or missing fields before approval.",
      action: openReviewCount ? "Open Human Review" : "Check review status"
    },
    {
      id: "upload-invoice-top",
      icon: SlidersHorizontal,
      name: "Process",
      status: workflowCount ? "complete" : invoiceCount ? "ready" : "not started",
      description: "Validate, check duplicates, match PO, and score risk.",
      action: "Run or review Process"
    },
    {
      id: "approval-inbox",
      icon: ShieldCheck,
      name: "Approve",
      status: blockedCount || pendingApprovalCount ? "needs attention" : invoiceCount ? "ready" : "not started",
      description: "Approve, reject, or hold invoices that need AP action.",
      action: "Open Approval Inbox"
    },
    {
      id: "erp-export",
      icon: Send,
      name: "Export",
      status: exportedCount ? "complete" : approvalReadyCount ? "ready" : "not started",
      description: "Export approval-ready invoices to the mock ERP adapter.",
      action: approvalReadyCount ? "Go to ERP Export" : "Check ERP readiness"
    },
    {
      id: "audit-trail",
      icon: History,
      name: "Audit",
      status: auditEventCount ? "complete" : "not started",
      description: "Verify what happened and who acted.",
      action: "View Audit Trail"
    }
  ] satisfies Array<{
    id: string;
    icon: LucideIcon;
    name: string;
    status: StageStatus;
    description: string;
    action: string;
  }>;

  return (
    <section className="scroll-mt-6 space-y-4" id="workflow-guide">
      <Card>
        <CardHeader className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <h2 className="text-lg font-semibold">AP Workflow Guide</h2>
            <p className="mt-1 text-sm text-muted">
              Follow the invoice from upload through OCR, review, approval, ERP export, and audit proof.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={priorityMode || "mock"} />
            <StatusBadge status={priorityMappingConfigured === true ? "Priority mapping saved" : priorityMappingConfigured === false ? "Priority mapping pending" : "Priority mapping in Admin"} />
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="rounded-md border border-blue-200 bg-blue-50 p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-sm font-semibold text-primary">Next recommended action</p>
                <h3 className="mt-1 text-lg font-semibold text-foreground">{nextAction.title}</h3>
                <p className="mt-1 text-sm text-muted">{nextAction.description}</p>
              </div>
              <Button
                onClick={nextAction.sectionId === "demo-login" ? onDemoLogin : () => onNavigate(nextAction.sectionId)}
                variant="primary"
              >
                {nextAction.buttonLabel}
              </Button>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-7">
            {stages.map((stage) => {
              const Icon = stage.icon;
              return (
                <button
                  className="rounded-md border border-border bg-white p-3 text-left transition hover:border-primary hover:bg-blue-50"
                  key={stage.name}
                  onClick={() => onNavigate(stage.id)}
                  type="button"
                >
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-slate-100 text-primary">
                      <Icon className="h-4 w-4" />
                    </span>
                    <StatusBadge status={stage.status} />
                  </div>
                  <p className="font-semibold">{stage.name}</p>
                  <p className="mt-1 min-h-[40px] text-xs text-muted">{stage.description}</p>
                  <p className="mt-3 text-xs font-medium text-primary">{stage.action}</p>
                </button>
              );
            })}
          </div>

          <details className="rounded-md border border-border bg-slate-50 px-4 py-3 text-sm">
            <summary className="cursor-pointer select-none font-medium">Demo checklist</summary>
            <div className="mt-3 grid gap-2 text-muted md:grid-cols-2">
              {[
                "Upload or use a seeded invoice",
                "Extract OCR",
                "Submit corrections if needed",
                "Process invoice",
                "Approve or hold in Approval Inbox",
                "Export approved invoice to mock ERP",
                "Review Audit Trail",
                "Validate Priority mapping",
                "Preview vendor/PO sync",
                "Generate import plan",
                "Import selected records into APFlow",
                "Confirm Imported Records"
              ].map((item) => (
                <div className="flex items-center gap-2" key={item}>
                  <CheckCircle2 className="h-4 w-4 text-success" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </details>
        </CardContent>
      </Card>
    </section>
  );
}

function getNextAction(input: {
  approvalReadyCount: number;
  auditEventCount: number;
  blockedCount: number;
  exportedCount: number;
  invoiceCount: number;
  isSignedIn: boolean;
  openReviewCount: number;
  pendingApprovalCount: number;
  priorityMappingConfigured?: boolean | null;
}) {
  if (!input.isSignedIn) {
    return {
      title: "Sign in to start the demo workflow.",
      description: "Use Demo login to load the AP manager workspace and protected invoice actions.",
      buttonLabel: "Demo login",
      sectionId: "demo-login"
    };
  }
  if (!input.invoiceCount) {
    return {
      title: "Upload an invoice to begin.",
      description: "Start with a supplier invoice PDF or image, then extract fields with OCR.",
      buttonLabel: "Go to Upload Invoice",
      sectionId: "upload-invoice-top"
    };
  }
  if (input.openReviewCount) {
    return {
      title: "Review extracted fields before processing.",
      description: "Some invoice fields need a human check. Correct them, save, then run Process again.",
      buttonLabel: "Open Human Review",
      sectionId: "ocr-review"
    };
  }
  if (input.blockedCount || input.pendingApprovalCount) {
    return {
      title: "Decide invoices waiting for AP approval.",
      description: "Open the Approval Inbox to approve, reject, or keep invoices on hold.",
      buttonLabel: "Open Approval Inbox",
      sectionId: "approval-inbox"
    };
  }
  if (input.approvalReadyCount) {
    return {
      title: "Export approval-ready invoices.",
      description: "Use the mock ERP export, then verify the result in Audit Trail.",
      buttonLabel: "Go to ERP Export",
      sectionId: "erp-export"
    };
  }
  if (input.exportedCount || input.auditEventCount) {
    return {
      title: "Verify the workflow proof.",
      description: "Audit Trail shows upload, review, approval, export, and Priority import activity.",
      buttonLabel: "View Audit Trail",
      sectionId: "audit-trail"
    };
  }
  if (input.priorityMappingConfigured === false) {
    return {
      title: "Validate Priority mapping when ready.",
      description: "For the ERP connector demo, save a mapping before previewing vendor and PO sync.",
      buttonLabel: "Open Admin",
      sectionId: "admin"
    };
  }
  return {
    title: "Review the dashboard sections below.",
    description: "The next available action depends on the selected invoice and tenant state.",
    buttonLabel: "Review Overview",
    sectionId: "overview"
  };
}
