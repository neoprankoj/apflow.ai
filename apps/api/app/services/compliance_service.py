from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core.schemas import (
    CanonicalInvoice,
    ComplianceCheckResult,
    ComplianceCheckStatus,
    ComplianceProfileRead,
    ComplianceSeverity,
    ComplianceSummary,
    InvoiceComplianceResult,
    InvoiceComplianceStatus,
)
from app.core.totals import reconcile_total

LEGAL_DISCLAIMER = (
    "Validation-only foundation. APFlow does not submit this invoice to any government, "
    "tax authority, PEPPOL network, or certified e-invoicing provider."
)


@dataclass(frozen=True)
class ComplianceProfileDefinition:
    key: str
    label: str
    country_or_region: str
    description: str
    required_fields: tuple[str, ...]
    recommended_fields: tuple[str, ...]
    fail_when_missing_recommended: tuple[str, ...] = ()
    requires_tax_total: bool = False


PROFILES: dict[str, ComplianceProfileDefinition] = {
    "generic_b2b": ComplianceProfileDefinition(
        key="generic_b2b",
        label="Generic B2B",
        country_or_region="Global",
        description="Minimum structured invoice data for future business-to-business e-invoicing workflows.",
        required_fields=("supplier_name", "invoice_number", "invoice_date", "currency", "grand_total"),
        recommended_fields=("supplier_tax_id", "buyer_name", "buyer_tax_id", "tax_total", "line_items", "payment_terms"),
    ),
    "israel_basic": ComplianceProfileDefinition(
        key="israel_basic",
        label="Israel Basic",
        country_or_region="Israel",
        description="Validation-only starter checks for Israeli invoice data readiness. This is not tax-authority submission.",
        required_fields=("supplier_name", "supplier_tax_id", "invoice_number", "invoice_date", "currency", "grand_total"),
        recommended_fields=("buyer_name", "buyer_tax_id", "tax_total", "line_items"),
        requires_tax_total=True,
    ),
    "eu_vat_basic": ComplianceProfileDefinition(
        key="eu_vat_basic",
        label="EU VAT Basic",
        country_or_region="European Union",
        description="Validation-only starter checks for EU VAT invoice data readiness. This is not PEPPOL or tax-platform integration.",
        required_fields=(
            "supplier_name",
            "supplier_tax_id",
            "invoice_number",
            "invoice_date",
            "currency",
            "subtotal",
            "tax_total",
            "grand_total",
        ),
        recommended_fields=("buyer_name", "buyer_tax_id", "line_items"),
        requires_tax_total=True,
    ),
    "us_basic": ComplianceProfileDefinition(
        key="us_basic",
        label="US Basic",
        country_or_region="United States",
        description="Validation-only starter checks for US invoice data readiness. This is not IRS submission.",
        required_fields=("supplier_name", "invoice_number", "invoice_date", "currency", "grand_total"),
        recommended_fields=("supplier_tax_id", "buyer_name", "buyer_tax_id", "line_items", "payment_terms"),
    ),
}


class ComplianceService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def list_compliance_profiles(self) -> list[ComplianceProfileRead]:
        return [
            ComplianceProfileRead(
                key=profile.key,
                label=profile.label,
                country_or_region=profile.country_or_region,
                description=profile.description,
                validation_only=True,
                certified_integration=False,
                required_fields=list(profile.required_fields),
                recommended_fields=list(profile.recommended_fields),
            )
            for profile in PROFILES.values()
        ]

    def validate_invoice_compliance(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        profile_key: str = "generic_b2b",
    ) -> InvoiceComplianceResult:
        profile = self._profile(profile_key)
        invoice_record = self.repository.get_invoice(tenant_id, invoice_id)
        return self.build_invoice_compliance_from_normalized_fields(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            invoice=invoice_record.canonical_invoice,
            profile=profile,
        )

    def get_compliance_summary(self, tenant_id: UUID, profile_key: str = "generic_b2b") -> ComplianceSummary:
        profile = self._profile(profile_key)
        results = [
            self.build_invoice_compliance_from_normalized_fields(
                tenant_id=tenant_id,
                invoice_id=record.invoice_id,
                invoice=record.canonical_invoice,
                profile=profile,
            )
            for record in self.repository.list_invoices(tenant_id)
        ]
        missing_counter: Counter[str] = Counter()
        warnings_count = 0
        for result in results:
            missing_counter.update(result.missing_required_fields)
            missing_counter.update(result.missing_recommended_fields)
            warnings_count += len(result.warnings)

        return ComplianceSummary(
            tenant_id=tenant_id,
            profile_key=profile.key,
            total_checked=len(results),
            compliant_count=sum(1 for result in results if result.status == InvoiceComplianceStatus.COMPLIANT_FOR_PROFILE),
            needs_review_count=sum(1 for result in results if result.status == InvoiceComplianceStatus.NEEDS_REVIEW),
            not_compliant_count=sum(1 for result in results if result.status == InvoiceComplianceStatus.NOT_COMPLIANT),
            warnings_count=warnings_count,
            common_missing_fields=dict(missing_counter.most_common(8)),
        )

    def build_invoice_compliance_from_normalized_fields(
        self,
        *,
        tenant_id: UUID,
        invoice_id: UUID,
        invoice: CanonicalInvoice,
        profile: ComplianceProfileDefinition,
    ) -> InvoiceComplianceResult:
        checks: list[ComplianceCheckResult] = []
        missing_required: list[str] = []
        missing_recommended: list[str] = []

        for field in profile.required_fields:
            present = self._field_present(invoice, field)
            checks.append(
                self._field_check(
                    field=field,
                    required=True,
                    present=present,
                    profile=profile,
                )
            )
            if not present:
                missing_required.append(field)

        for field in profile.recommended_fields:
            if field in profile.required_fields:
                continue
            present = self._field_present(invoice, field)
            checks.append(
                self._field_check(
                    field=field,
                    required=False,
                    present=present,
                    profile=profile,
                )
            )
            if not present:
                missing_recommended.append(field)

        checks.extend(self._content_checks(invoice, profile))

        has_failures = any(check.status == ComplianceCheckStatus.FAIL for check in checks)
        has_warnings = any(check.status == ComplianceCheckStatus.WARNING for check in checks)
        if has_failures:
            status = InvoiceComplianceStatus.NOT_COMPLIANT
            summary = f"Invoice is missing required data for {profile.label} validation."
        elif has_warnings:
            status = InvoiceComplianceStatus.NEEDS_REVIEW
            summary = f"Invoice has the required data for {profile.label}, but recommended compliance fields need review."
        else:
            status = InvoiceComplianceStatus.COMPLIANT_FOR_PROFILE
            summary = f"Invoice has the minimum structured data for {profile.label} validation."

        return InvoiceComplianceResult(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            profile_key=profile.key,
            status=status,
            summary=summary,
            checks=checks,
            missing_required_fields=missing_required,
            missing_recommended_fields=missing_recommended,
            warnings=[check.message for check in checks if check.status == ComplianceCheckStatus.WARNING],
            generated_at=datetime.now(UTC),
            legal_disclaimer=LEGAL_DISCLAIMER,
        )

    def _profile(self, profile_key: str) -> ComplianceProfileDefinition:
        profile = PROFILES.get(profile_key)
        if profile is None:
            raise ValueError(f"Unsupported compliance profile: {profile_key}")
        return profile

    def _field_present(self, invoice: CanonicalInvoice, field: str) -> bool:
        if field == "line_items":
            return bool(invoice.line_items)
        if field in {"buyer_name", "buyer_tax_id", "payment_terms"}:
            return False
        value = getattr(invoice, field, None)
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (int, float)):
            return value > 0
        return value is not None

    def _field_check(
        self,
        *,
        field: str,
        required: bool,
        present: bool,
        profile: ComplianceProfileDefinition,
    ) -> ComplianceCheckResult:
        label = FIELD_LABELS.get(field, field.replace("_", " ").title())
        if present:
            return ComplianceCheckResult(
                key=f"{field}_present",
                label=f"{label} present",
                status=ComplianceCheckStatus.PASS,
                severity=ComplianceSeverity.LOW,
                field=field,
                message=f"{label} is available for {profile.label} validation.",
            )
        if required:
            return ComplianceCheckResult(
                key=f"{field}_missing",
                label=f"{label} missing",
                status=ComplianceCheckStatus.FAIL,
                severity=ComplianceSeverity.HIGH,
                field=field,
                message=f"{label} is required for {profile.label} validation.",
                next_step=f"Capture or correct {label.lower()} before using this invoice in e-invoicing workflows.",
            )
        return ComplianceCheckResult(
            key=f"{field}_recommended_missing",
            label=f"{label} recommended",
            status=ComplianceCheckStatus.WARNING,
            severity=ComplianceSeverity.MEDIUM,
            field=field,
            message=f"{label} is recommended for {profile.label} validation.",
            next_step=f"Add {label.lower()} when available from the supplier or buyer master data.",
        )

    def _content_checks(self, invoice: CanonicalInvoice, profile: ComplianceProfileDefinition) -> list[ComplianceCheckResult]:
        checks: list[ComplianceCheckResult] = []
        currency = (invoice.currency or "").strip().upper()
        if len(currency) == 3 and currency.isalpha():
            checks.append(
                ComplianceCheckResult(
                    key="currency_format",
                    label="Currency format",
                    status=ComplianceCheckStatus.PASS,
                    severity=ComplianceSeverity.LOW,
                    field="currency",
                    message="Currency is a 3-letter code.",
                )
            )
        else:
            checks.append(
                ComplianceCheckResult(
                    key="currency_format",
                    label="Currency format",
                    status=ComplianceCheckStatus.FAIL,
                    severity=ComplianceSeverity.HIGH,
                    field="currency",
                    message="Currency should be a 3-letter code for e-invoicing validation.",
                    next_step="Correct the currency before using this invoice in e-invoicing workflows.",
                )
            )

        if profile.requires_tax_total and invoice.tax_total <= 0:
            checks.append(
                ComplianceCheckResult(
                    key="tax_total_required_for_profile",
                    label="Tax amount required",
                    status=ComplianceCheckStatus.FAIL,
                    severity=ComplianceSeverity.HIGH,
                    field="tax_total",
                    message=f"{profile.label} expects a tax/VAT amount when validating VAT-style invoices.",
                    next_step="Capture tax amount or confirm the invoice is exempt before future e-invoicing submission.",
                )
            )

        reconciliation = reconcile_total(
            subtotal=invoice.subtotal,
            tax_total=invoice.tax_total,
            shipping_amount=invoice.shipping_amount,
            fee_total=invoice.fee_total,
            discount_total=invoice.discount_total,
            grand_total=invoice.grand_total,
            components_complete=invoice.total_components_complete,
        )
        if reconciliation.components_complete and reconciliation.matches:
            checks.append(
                ComplianceCheckResult(
                    key="grand_total_reconciles",
                    label="Grand total reconciles",
                    status=ComplianceCheckStatus.PASS,
                    severity=ComplianceSeverity.LOW,
                    field="grand_total",
                    message=f"Grand total matches {reconciliation.formula_label}.",
                )
            )
        elif reconciliation.components_complete:
            checks.append(
                ComplianceCheckResult(
                    key="grand_total_mismatch",
                    label="Grand total mismatch",
                    status=ComplianceCheckStatus.FAIL,
                    severity=ComplianceSeverity.HIGH,
                    field="grand_total",
                    message=(
                        f"Grand total does not match {reconciliation.formula_label}: "
                        f"{reconciliation.expected_total:.2f} vs {reconciliation.actual_total:.2f}."
                    ),
                    next_step="Review invoice totals and discounts before future e-invoicing workflows.",
                )
            )
        else:
            checks.append(
                ComplianceCheckResult(
                    key="grand_total_components_incomplete",
                    label="Total components incomplete",
                    status=ComplianceCheckStatus.WARNING,
                    severity=ComplianceSeverity.MEDIUM,
                    field="grand_total",
                    message="Visible components are incomplete, so APFlow cannot fully reconcile the grand total.",
                    next_step="Capture subtotal, tax, shipping, fees, and discounts when available.",
                )
            )
        return checks


FIELD_LABELS = {
    "supplier_name": "Supplier name",
    "supplier_tax_id": "Supplier tax ID",
    "buyer_name": "Buyer name",
    "buyer_tax_id": "Buyer tax ID",
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "currency": "Currency",
    "subtotal": "Taxable amount",
    "tax_total": "Tax/VAT amount",
    "grand_total": "Grand total",
    "line_items": "Line items",
    "payment_terms": "Payment terms",
}
