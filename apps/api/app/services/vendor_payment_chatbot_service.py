import re
from datetime import date, datetime
from uuid import UUID

from app.core.repositories import InMemoryAPRepository, InvoiceRecord
from app.core.schemas import (
    VendorChatIntent,
    VendorChatRequest,
    VendorChatResponse,
    VendorInvoiceListItem,
    VendorSafePaymentStatus,
)
from app.core.vendor_portal import invoice_is_visible_to_vendor, vendor_invoice_list_item, vendor_invoice_status


UNSAFE_TERMS = (
    "fraud",
    "risk",
    "risk score",
    "audit",
    "metadata",
    "approval policy",
    "approver",
    "approved by",
    "internal note",
    "internal notes",
    "erp config",
    "erp log",
    "erp logs",
    "duplicate",
    "token",
    "hash",
    "tenant",
)


class VendorPaymentChatbotService:
    """Deterministic vendor-safe invoice/payment chatbot.

    This service intentionally uses simple retrieval and rules. It never calls an
    external model and only formats the vendor-safe invoice/payment projection.
    """

    def __init__(self, repository: InMemoryAPRepository) -> None:
        self.repository = repository

    def answer(self, request: VendorChatRequest, vendor_id: UUID, vendor_name: str | None = None) -> VendorChatResponse:
        question = request.question.strip()
        intent = self._classify_intent(question)
        visible_invoices = self._visible_invoices(request.tenant_id, vendor_id, vendor_name)

        if intent == VendorChatIntent.UNSUPPORTED_OR_UNSAFE:
            return self._refusal_response(intent, "unsafe_topic")

        if intent == VendorChatIntent.HELP:
            return VendorChatResponse(
                intent=VendorChatIntent.HELP,
                answer=(
                    "I can answer vendor-safe questions about invoice status, payment status, scheduled dates, "
                    "paid invoices, pending invoices, and disputed invoices."
                ),
                confidence="high",
                safe_suggestions=self._suggestions(),
            )

        if intent in {
            VendorChatIntent.LIST_PENDING_INVOICES,
            VendorChatIntent.LIST_PAID_INVOICES,
            VendorChatIntent.LIST_DISPUTED_INVOICES,
            VendorChatIntent.LIST_ALL_VISIBLE_INVOICES,
        }:
            return self._list_response(request.tenant_id, visible_invoices, intent)

        invoice = self._resolve_invoice(request, question, visible_invoices)
        if invoice is None:
            return VendorChatResponse(
                intent=intent,
                answer="I could not find that invoice for this vendor access.",
                confidence="medium",
                safe_suggestions=self._suggestions(),
                refused=False,
                escalated=True,
            )

        return self._invoice_response(request.tenant_id, invoice, intent)

    def _visible_invoices(self, tenant_id: UUID, vendor_id: UUID, vendor_name: str | None) -> list[InvoiceRecord]:
        return [
            invoice
            for invoice in self.repository.list_invoices(tenant_id)
            if invoice_is_visible_to_vendor(invoice, vendor_id, vendor_name)
        ]

    def _resolve_invoice(
        self,
        request: VendorChatRequest,
        question: str,
        invoices: list[InvoiceRecord],
    ) -> InvoiceRecord | None:
        if request.invoice_id is not None:
            return next((invoice for invoice in invoices if invoice.invoice_id == request.invoice_id), None)
        invoice_number = request.invoice_number or self._extract_invoice_number(question)
        if invoice_number:
            normalized = _normalize_invoice_number(invoice_number)
            return next(
                (
                    invoice
                    for invoice in invoices
                    if _normalize_invoice_number(invoice.canonical_invoice.invoice_number) == normalized
                ),
                None,
            )
        if len(invoices) == 1:
            return invoices[0]
        return None

    def _invoice_response(self, tenant_id: UUID, invoice: InvoiceRecord, intent: VendorChatIntent) -> VendorChatResponse:
        safe_status = vendor_invoice_status(self.repository, tenant_id, invoice)
        payment = safe_status.payment_status_detail
        invoice_number = safe_status.invoice_number

        if intent in {VendorChatIntent.INVOICE_PAID_STATUS, VendorChatIntent.PAYMENT_STATUS} and _payment_value(payment) == "paid":
            answer = f"Invoice {invoice_number} is marked as paid{_date_suffix(payment.paid_at, ' on ')}."
        elif intent == VendorChatIntent.INVOICE_PAID_STATUS:
            answer = f"Invoice {invoice_number} is not marked as paid yet. Current status: {_payment_label(payment, safe_status.status)}."
        elif intent == VendorChatIntent.INVOICE_DUE_OR_SCHEDULED_DATE:
            if payment and payment.scheduled_payment_date:
                answer = f"Invoice {invoice_number} is scheduled for payment on {_format_date(payment.scheduled_payment_date)}."
            elif safe_status.due_date:
                answer = f"Invoice {invoice_number} has due date {_format_date(safe_status.due_date)}, but scheduled payment status is not available yet."
            else:
                answer = f"Invoice {invoice_number} is visible to this vendor access, but scheduled payment status is not available yet."
        elif intent in {VendorChatIntent.INVOICE_PAYMENT_STATUS, VendorChatIntent.PAYMENT_STATUS}:
            if payment:
                answer = f"Invoice {invoice_number} payment status: {payment.safe_status_label}. {payment.safe_message}"
            else:
                answer = f"Invoice {invoice_number} is visible to this vendor access, but payment status is not available yet."
        elif intent == VendorChatIntent.MISSING_INFORMATION:
            if safe_status.missing_information:
                answer = f"Invoice {invoice_number} needs more information for: {', '.join(safe_status.missing_information)}."
            else:
                answer = f"Invoice {invoice_number} does not show a current missing-information request."
        elif intent == VendorChatIntent.REJECTION_REASON_PUBLIC:
            answer = safe_status.public_message
        elif intent == VendorChatIntent.APPROVAL_STATUS:
            answer = f"Invoice {invoice_number} is {str(safe_status.status).replace('_', ' ')}."
        else:
            answer = f"Invoice {invoice_number} is {str(safe_status.status).replace('_', ' ')}."

        item = vendor_invoice_list_item(self.repository, tenant_id, invoice)
        return VendorChatResponse(
            intent=intent,
            answer=answer,
            invoice_id=invoice.invoice_id,
            status=safe_status.status,
            confidence="high",
            matched_invoice_ids=[invoice.invoice_id],
            matched_invoices=[item],
            safe_suggestions=self._suggestions(),
            refused=False,
            escalated=False,
        )

    def _list_response(
        self,
        tenant_id: UUID,
        invoices: list[InvoiceRecord],
        intent: VendorChatIntent,
    ) -> VendorChatResponse:
        items = [vendor_invoice_list_item(self.repository, tenant_id, invoice) for invoice in invoices]
        filtered = self._filter_items(items, intent)
        if not filtered:
            answer = self._empty_list_answer(intent)
        else:
            preview = ", ".join(_invoice_item_summary(item) for item in filtered[:5])
            remaining = len(filtered) - min(len(filtered), 5)
            answer = f"{self._list_answer_prefix(intent, len(filtered))}: {preview}."
            if remaining > 0:
                answer += f" {remaining} more invoice{'' if remaining == 1 else 's'} also match."
        return VendorChatResponse(
            intent=intent,
            answer=answer,
            confidence="high",
            matched_invoice_ids=[item.invoice_id for item in filtered],
            matched_invoices=filtered[:10],
            safe_suggestions=self._suggestions(),
            refused=False,
        )

    def _filter_items(self, items: list[VendorInvoiceListItem], intent: VendorChatIntent) -> list[VendorInvoiceListItem]:
        if intent == VendorChatIntent.LIST_PENDING_INVOICES:
            return [
                item
                for item in items
                if str(item.payment_status or item.status) in {"pending", "not_started", "scheduled", "under_review", "received"}
            ]
        if intent == VendorChatIntent.LIST_PAID_INVOICES:
            return [item for item in items if str(item.payment_status or item.status) == "paid"]
        if intent == VendorChatIntent.LIST_DISPUTED_INVOICES:
            return [item for item in items if str(item.payment_status or "") == "disputed"]
        return items

    def _classify_intent(self, question: str) -> VendorChatIntent:
        normalized = question.casefold()
        if any(term in normalized for term in UNSAFE_TERMS):
            return VendorChatIntent.UNSUPPORTED_OR_UNSAFE
        if any(term in normalized for term in ("help", "what can you answer", "what can i ask")):
            return VendorChatIntent.HELP
        if any(term in normalized for term in ("all invoices", "show invoices", "list invoices", "my invoices")):
            return VendorChatIntent.LIST_ALL_VISIBLE_INVOICES
        if "disputed" in normalized or "dispute" in normalized:
            return VendorChatIntent.LIST_DISPUTED_INVOICES
        if "pending" in normalized or "still open" in normalized or "not paid" in normalized:
            return VendorChatIntent.LIST_PENDING_INVOICES
        if "paid invoices" in normalized or "which invoices are paid" in normalized:
            return VendorChatIntent.LIST_PAID_INVOICES
        if "when" in normalized or "scheduled" in normalized or "pay date" in normalized or "payment date" in normalized:
            return VendorChatIntent.INVOICE_DUE_OR_SCHEDULED_DATE
        if "paid" in normalized:
            return VendorChatIntent.INVOICE_PAID_STATUS
        if "payment" in normalized or "status" in normalized:
            return VendorChatIntent.INVOICE_PAYMENT_STATUS
        if any(term in normalized for term in ("approved", "approval", "review")):
            return VendorChatIntent.APPROVAL_STATUS
        if any(term in normalized for term in ("missing", "information", "documents", "correction")):
            return VendorChatIntent.MISSING_INFORMATION
        if any(term in normalized for term in ("reject", "rejected", "declined")):
            return VendorChatIntent.REJECTION_REASON_PUBLIC
        if any(term in normalized for term in ("received", "submitted", "got my invoice", "invoice")):
            return VendorChatIntent.INVOICE_RECEIVED
        return VendorChatIntent.UNSUPPORTED_OR_UNSAFE

    def _extract_invoice_number(self, question: str) -> str | None:
        patterns = [
            r"(?i)\binvoice\s*(?:number|#|no\.?)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,40})",
            r"(?i)#\s*([A-Z0-9][A-Z0-9._/-]{1,40})",
            r"(?i)\b(INV[-_./]?[A-Z0-9._/-]{1,40})\b",
            r"(?i)\b(\d{3,})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, question)
            if match:
                return match.group(1).strip(" .,:;")
        return None

    def _refusal_response(self, intent: VendorChatIntent, reason: str) -> VendorChatResponse:
        return VendorChatResponse(
            intent=intent,
            answer="I can only answer vendor-safe invoice and payment-status questions. For anything else, please contact AP team.",
            confidence="high",
            safe_suggestions=self._suggestions(),
            refused=True,
            refusal_reason=reason,
            escalated=True,
        )

    def _suggestions(self) -> list[str]:
        return [
            "What is the status of invoice 40100?",
            "Has this invoice been paid?",
            "When is payment scheduled?",
            "Which invoices are pending?",
        ]

    def _empty_list_answer(self, intent: VendorChatIntent) -> str:
        if intent == VendorChatIntent.LIST_PENDING_INVOICES:
            return "I do not see any pending invoices for this vendor access."
        if intent == VendorChatIntent.LIST_PAID_INVOICES:
            return "I do not see any paid invoices for this vendor access."
        if intent == VendorChatIntent.LIST_DISPUTED_INVOICES:
            return "I do not see any disputed invoices for this vendor access."
        return "I do not see any vendor-visible invoices for this access."

    def _list_answer_prefix(self, intent: VendorChatIntent, count: int) -> str:
        noun = "invoice" if count == 1 else "invoices"
        if intent == VendorChatIntent.LIST_PENDING_INVOICES:
            return f"I found {count} pending {noun}"
        if intent == VendorChatIntent.LIST_PAID_INVOICES:
            return f"I found {count} paid {noun}"
        if intent == VendorChatIntent.LIST_DISPUTED_INVOICES:
            return f"I found {count} disputed {noun}"
        return f"I found {count} visible {noun}"


def _normalize_invoice_number(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _payment_value(payment: VendorSafePaymentStatus | None) -> str | None:
    return str(payment.status) if payment else None


def _payment_label(payment: VendorSafePaymentStatus | None, fallback_status) -> str:
    if payment is not None:
        return payment.safe_status_label
    return str(fallback_status).replace("_", " ")


def _date_suffix(value: str | date | datetime | None, prefix: str) -> str:
    if value is None:
        return ""
    return f"{prefix}{_format_date(value)}"


def _format_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return f"{value:%b} {value.day}, {value:%Y}"
    if isinstance(value, date):
        return f"{value:%b} {value.day}, {value:%Y}"
    return value


def _invoice_item_summary(item: VendorInvoiceListItem) -> str:
    status = str(item.payment_status or item.status).replace("_", " ")
    return f"{item.invoice_number} ({status})"
