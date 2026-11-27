
from pydantic import BaseModel, Field
from typing import List, Optional
from decimal import Decimal

class Address(BaseModel):
    company: str
    street: str
    zip_code: str
    city: str
    country: str
    email: Optional[str] = None
    phone: Optional[str] = None

    additional_name: Optional[str] = None
    address_specification: Optional[str] = None
    district: Optional[str] = None

class Debtor(BaseModel):
    company: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    billing_address: Address
    delivery_address: Address

class OrderItem(BaseModel):
    sku: str
    description: str
    quantity: Decimal
    unit_net_price: Decimal
    vat_percentage: Decimal
    discount: Decimal = Decimal("0.0")

class OrderData(BaseModel):
    external_reference: str
    order_date: str
    currency: str
    debtor: Debtor
    payment_method: str
    paid_status: str
    payment_date: Optional[str] = None
    items: List[OrderItem]
    total_net: Decimal
    total_vat: Decimal
    total_gross: Decimal