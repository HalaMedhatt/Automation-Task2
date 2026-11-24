from decimal import Decimal
from src.models.order import OrderData

class DataValidationError(Exception):
    """Custom exception raised when extracted data fails business logic checks."""
    pass

def validate_order_totals(order: OrderData) -> None:
    """
    Validates that the extracted line items and totals are mathematically correct.
    Raises DataValidationError if there is a mismatch.
    """
    calculated_net_total = Decimal("0.00")
    
    # 1. Validate each line item
    for item in order.items:
        # Safeguard: if AI returns 0.1 instead of 10, convert it
        discount_val = item.discount
        if Decimal("0") < discount_val <= Decimal("1"):
            discount_val = discount_val * Decimal("100")

        discount_multiplier = Decimal("1") - (discount_val / Decimal("100"))
        expected_line_net = (item.quantity * item.unit_net_price * discount_multiplier).quantize(Decimal("0.01"))
        
        # Debug print to see exactly what the AI extracted for each line
        print(f"Validating Item: {item.sku} | Qty: {item.quantity} | Net: {item.unit_net_price} | Disc: {item.discount}% | Line Total: {expected_line_net}")
        
        calculated_net_total += expected_line_net

    # 2. Check Total Net
    calculated_net_total = calculated_net_total.quantize(Decimal("0.01"))
    if calculated_net_total != order.total_net:
        raise DataValidationError(
            f"Net Total mismatch! Extracted: {order.total_net}, Calculated: {calculated_net_total}"
        )

    # 3. Check Gross Total (Net + VAT)
    calculated_gross = (order.total_net + order.total_vat).quantize(Decimal("0.01"))
    if calculated_gross != order.total_gross:
        raise DataValidationError(
            f"Gross Total mismatch! Extracted: {order.total_gross}, Calculated: {calculated_gross}"
        )
        
    print("✅ Validation Passed: All totals and calculations are mathematically correct.")