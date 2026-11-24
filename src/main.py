from src.extraction.gemini_client import extract_order_from_image
from src.models.validation import validate_order_totals

if __name__ == "__main__":
    print("Starting the Image-to-Cash Automation pipeline...")
    
    # Updated path to the data/input folder
    image_path = "data/input/order.png" 
    
    try:
        # Step 1: Extract data using Gemini
        order_data = extract_order_from_image(image_path)
        
        # Step 2: Validate the extracted data mathematically
        validate_order_totals(order_data)
        
        # Step 3: Print full data for verification
        print("\n--- Extracted Order Data ---")
        print(f"Ref: {order_data.external_reference} | Date: {order_data.order_date}")
        print(f"Debtor: {order_data.debtor.company}")
        print(f"Billing Address: {order_data.debtor.billing_address.street}, {order_data.debtor.billing_address.zip_code} {order_data.debtor.billing_address.city}")
        print(f"Delivery Address: {order_data.debtor.delivery_address.street}, {order_data.debtor.delivery_address.zip_code} {order_data.debtor.delivery_address.city}")
        
        print("\nItems:")
        for item in order_data.items:
            print(f" - SKU: {item.sku} | Qty: {item.quantity} | Net: {item.unit_net_price} | Disc: {item.discount}% | VAT: {item.vat_percentage}%")
            
        print(f"\nTotals -> Net: {order_data.total_net} | VAT: {order_data.total_vat} | Gross: {order_data.total_gross}")
        
        print("\nPayment Info:")
        print(f"Method: {order_data.payment_method} | Status: {order_data.paid_status} | Date: {order_data.payment_date}")



    except Exception as e:
        print(f"\n❌ Pipeline stopped: {e}")
