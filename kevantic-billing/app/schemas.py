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
    internal_notes: str | None = None
    terms_text: str | None = None
    opportunity_name: str | None = None
    sales_owner: str | None = None
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
    internal_notes: str | None = None
    terms_text: str | None = None
    opportunity_name: str | None = None
    sales_owner: str | None = None
    requires_approval: bool = False
    approved_by: str | None = None
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
    party_name: str | None = None

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


class PaymentOut(BaseModel):
    id: UUID
    invoice_id: UUID
    amount: Decimal
    payment_date: date
    method: str
    reference: str | None
    notes: str | None
    created_at: datetime

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
    balance_due: Decimal | None = None
    notes: str | None
    lines: list[InvoiceLineOut] = []
    payments: list[PaymentOut] = []
    party_name: str | None = None

    model_config = {"from_attributes": True}


class MarkPaidIn(BaseModel):
    amount: Decimal | None = None
    method: str = "bank_transfer"
    reference: str | None = None
    notes: str | None = None
    payment_date: date | None = None


class CompanyProfileIn(BaseModel):
    legal_name: str
    gstin: str | None = None
    pan: str | None = None
    state: str = "Maharashtra"
    state_code: str = "27"
    address: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    bank_ifsc: str | None = None
    bank_branch: str | None = None
    upi_id: str | None = None
    default_terms: str | None = None
    invoice_footer: str | None = None
    currency: str = "INR"
    lut_filed: bool = False
    quote_validity_days: int = 30
    discount_approval_threshold: Decimal = Decimal("15.00")


class CompanyProfileOut(CompanyProfileIn):
    id: int
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
