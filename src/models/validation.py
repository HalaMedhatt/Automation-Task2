
import logging
from decimal import Decimal, ROUND_HALF_UP

from src.models.order import OrderData


logger = logging.getLogger(__name__)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MONEY_PRECISION = Decimal("0.01")


class DataValidationError(Exception):
    """Raised when extracted data fails business validation."""


def validate_order_totals(order: OrderData) -> None:
    """
    Validate extracted order data before interacting with Fakturama.

    Checks required data, item values, discounts, VAT, and
    financial totals without silently modifying extracted values.
    """

    # 1. Validate essential order and debtor data.

    if not order.items:
        raise DataValidationError("Order contains no items.")

    if not order.debtor.company or not order.debtor.company.strip():
        raise DataValidationError("Debtor company name is missing.")

    if (
        not order.debtor.billing_address.street
        or not order.debtor.billing_address.city
    ):
        raise DataValidationError("Billing address is incomplete.")

    if order.paid_status == "PAID" and not order.payment_date:
        raise DataValidationError(
            "Order is PAID but payment date is missing."
        )

    calculated_net_total = ZERO
    calculated_vat_total = ZERO

    # 2. Validate every item and calculate financial values.

    for index, item in enumerate(order.items, start=1):

        if item.quantity <= ZERO:
            raise DataValidationError(
                f"Item {index}: Quantity must be positive."
            )

        if item.unit_net_price < ZERO:
            raise DataValidationError(
                f"Item {index}: Unit net price cannot be negative."
            )

        if not ZERO <= item.discount <= HUNDRED:
            raise DataValidationError(
                f"Item {index}: Invalid discount percentage."
            )

        if not ZERO <= item.vat_percentage <= HUNDRED:
            raise DataValidationError(
                f"Item {index}: Invalid VAT percentage."
            )

        # Percentages must already be normalized by extraction.
        # Never silently convert or modify extracted discounts.

        discount_multiplier = (
            Decimal("1") - item.discount / HUNDRED
        )

        # Calculate the net line total after discount.

        line_net = (
            item.quantity
            * item.unit_net_price
            * discount_multiplier
        ).quantize(
            MONEY_PRECISION,
            rounding=ROUND_HALF_UP
        )

        # Calculate VAT on the discounted net amount.

        line_vat = (
            line_net * item.vat_percentage / HUNDRED
        ).quantize(
            MONEY_PRECISION,
            rounding=ROUND_HALF_UP
        )

        calculated_net_total += line_net
        calculated_vat_total += line_vat

        logger.info(
            "Item %s validated | Net: %s | VAT: %s",
            index,
            line_net,
            line_vat
        )

    # 3. Verify calculated net total against the source image.

    if calculated_net_total != order.total_net:
        raise DataValidationError(
            f"Net Total mismatch! "
            f"Source: {order.total_net}, "
            f"Calculated: {calculated_net_total}"
        )

    # 4. Verify calculated VAT against the source image.

    if calculated_vat_total != order.total_vat:
        raise DataValidationError(
            f"VAT Total mismatch! "
            f"Source: {order.total_vat}, "
            f"Calculated: {calculated_vat_total}"
        )

    # 5. Verify calculated gross total against the source image.

    calculated_gross = (
        calculated_net_total + calculated_vat_total
    ).quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP
    )

    if calculated_gross != order.total_gross:
        raise DataValidationError(
            f"Gross Total mismatch! "
            f"Source: {order.total_gross}, "
            f"Calculated: {calculated_gross}"
        )

    logger.info(
        "Validation passed | Items: %s | Net: %s | VAT: %s | Gross: %s",
        len(order.items),
        calculated_net_total,
        calculated_vat_total,
        calculated_gross
    )
