ORDER_EXTRACTION_PROMPT = """
Extract the order data from this image. Return ONLY a valid JSON object matching this schema exactly.
Do not include markdown formatting like ```json.
Extract additional_name, address_specification, and district
only when explicitly supplied by the source image.
Return null for missing optional values.
Do not invent or duplicate address information.
{
  "external_reference": "string",
  "order_date": "YYYY-MM-DD",
  "currency": "string",
  "debtor": {
    "company": "string",
    "first_name": "string or null",
    "last_name": "string or null",
    "billing_address": {
      "company": "string",
      "street": "string",
      "zip_code": "string",
      "city": "string",
      "country": "string",
      "email": "string or null",
      "phone": "string or null",
      "additional_name": "string or null",
      "address_specification": "string or null",
      "district": "string or null" 
    },
    "delivery_address": {
      "company": "string",
      "street": "string",
      "zip_code": "string",
      "city": "string",
      "country": "string",
      "additional_name": "string or null",
      "address_specification": "string or null",
      "district": "string or null"
    }
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