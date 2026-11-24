ORDER_EXTRACTION_PROMPT = """
Extract the order data from this image. Return ONLY a valid JSON object matching this schema exactly.
Do not include markdown formatting like ```json.
{
  "external_reference": "string",
  "order_date": "YYYY-MM-DD",
  "currency": "string",
  "debtor": {
    "company": "string",
    "first_name": "string or null",
    "last_name": "string or null",
    "billing_address": {"company": "string", "street": "string", "zip_code": "string", "city": "string", "country": "string", "email": "string or null", "phone": "string or null"},
    "delivery_address": {"company": "string", "street": "string", "zip_code": "string", "city": "string", "country": "string"}
  },
  "payment_method": "string (e.g., Bank Transfer)",
  "paid_status": "PAID or UNPAID",
  "payment_date": "YYYY-MM-DD or null",
  "items": [
    {
      "sku": "string", 
      "description": "string", 
      "quantity": float, 
      "unit_net_price": float, 
      "vat_percentage": float (e.g., 19.0 for 19%, NOT 0.19), 
      "discount": float (e.g., 10.0 for 10%, NOT 0.1)
    }
  ],
  "total_net": float,
  "total_vat": float,
  "total_gross": float
}
"""