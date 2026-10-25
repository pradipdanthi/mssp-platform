from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PartyIn(BaseModel):
    legal_name: str
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None
    billing_address: str | None = None
    state: str = "Maharashtra"
    state_code: str = "27"
    country: str = "India"
    gstin: str | None = None
    pan: str | None = None
    is_export: bool = False
    payment_terms_days: int = 15
    currency: str = "INR"
    notes: str | None = None


class PartyOut(PartyIn):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class CatalogItemOut(BaseModel):
    id: UUID
    sku: str
    name: str
    description: str | None
    product_family: str
    billing_model: str
    unit_label: str
    list_price: Decimal
    currency: str
    gst_rate: Decimal
    hsn_sac: str | None
    min_qty: int
    active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class CatalogItemUpdate(BaseModel):
    list_price: Decimal | None = None
    name: str | None = None
    description: str | None = None
    active: bool | None = None
    gst_rate: Decimal | None = None
    min_qty: int | None = None


class QuoteLineIn(BaseModel):
    catalog_item_id: UUID | None = None
    sku: str | None = None
    description: str | None = None
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal | None = None
    discount_percent: Decimal = Decimal("0")
    gst_rate: Decimal | None = None
    hsn_sac: str | None = None
    billing_model: str | None = None


class QuoteCreate(BaseModel):
    party_id: UUID
    lines: list[QuoteLineIn]
    term_months: int = 12
    discount_percent: Decimal = Decimal("0")
    notes: str | None = None
    tax_mode: str = "auto"
    status: str = "draft"


class QuoteLineOut(BaseModel):
    id: UUID
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    gst_rate: Decimal
    hsn_sac: str | None
    line_subtotal: Decimal
    line_taxable: Decimal
    line_tax: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class QuoteOut(BaseModel):
    id: UUID
    quote_number: str
    party_id: UUID
    status: str
    currency: str
    issue_date: date
    valid_until: date | None
    term_months: int
    discount_percent: Decimal
    notes: str | None
    place_of_supply_state: str | None
    place_of_supply_code: str | None
    tax_mode: str
    subtotal: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    lines: list[QuoteLineOut] = []

    model_config = {"from_attributes": True}


class InvoiceLineOut(BaseModel):
    id: UUID
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    gst_rate: Decimal
    hsn_sac: str | None
    line_subtotal: Decimal
    line_taxable: Decimal
    line_tax: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class InvoiceOut(BaseModel):
    id: UUID
    invoice_number: str
    party_id: UUID
    quote_id: UUID | None
    status: str
    invoice_type: str
    currency: str
    issue_date: date
    due_date: date | None
    place_of_supply_state: str | None
    place_of_supply_code: str | None
    tax_mode: str
    subtotal: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    notes: str | None
    lines: list[InvoiceLineOut] = []

    model_config = {"from_attributes": True}


class MarkPaidIn(BaseModel):
    amount: Decimal | None = None
