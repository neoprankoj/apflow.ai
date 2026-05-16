from dataclasses import dataclass


@dataclass(frozen=True)
class TotalReconciliation:
    expected_total: float
    actual_total: float
    difference: float
    matches: bool
    components_complete: bool


def reconcile_total(
    *,
    subtotal: float,
    tax_total: float,
    shipping_amount: float = 0,
    fee_total: float = 0,
    discount_total: float = 0,
    grand_total: float,
    components_complete: bool,
    tolerance: float = 0.02,
) -> TotalReconciliation:
    expected_total = round(subtotal + tax_total + shipping_amount + fee_total - discount_total, 2)
    actual_total = round(grand_total, 2)
    difference = round(expected_total - actual_total, 2)
    return TotalReconciliation(
        expected_total=expected_total,
        actual_total=actual_total,
        difference=difference,
        matches=abs(difference) <= tolerance,
        components_complete=components_complete,
    )
