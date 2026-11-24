from decimal import Decimal, ROUND_HALF_UP

def calculate_gross_price(net_price: Decimal, vat_percent: Decimal) -> Decimal:
    multiplier = Decimal(1) + (vat_percent / Decimal(100))
    return (net_price * multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def calculate_line_total(qty: Decimal, net_price: Decimal, discount_percent: Decimal) -> Decimal:
    discount_multiplier = Decimal(1) - (discount_percent / Decimal(100))
    return (qty * net_price * discount_multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)