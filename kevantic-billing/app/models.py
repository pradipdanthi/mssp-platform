from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Party(Base):
    __tablename__ = "parties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    billing_address: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(64), default="Maharashtra")
    state_code: Mapped[str] = mapped_column(String(8), default="27")
    country: Mapped[str] = mapped_column(String(64), default="India")
    gstin: Mapped[str | None] = mapped_column(String(20))
    pan: Mapped[str | None] = mapped_column(String(20))
    is_export: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=15)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    quotes: Mapped[list[Quote]] = relationship(back_populates="party")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="party")


class CatalogItem(Base):
    __tablename__ = "catalog_items"
    __table_args__ = (UniqueConstraint("sku", name="uq_catalog_sku"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    product_family: Mapped[str] = mapped_column(String(64), nullable=False)
    # subscription | one_time | usage
    billing_model: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_label: Mapped[str] = mapped_column(String(64), default="unit")
    list_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    # GST rate percent e.g. 18.00
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("18.00"))
    hsn_sac: Mapped[str | None] = mapped_column(String(16))
    vendor_name: Mapped[str | None] = mapped_column(String(128))
    min_qty: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    quote_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parties.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | sent | accepted | declined | expired | invoiced
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    issue_date: Mapped[date] = mapped_column(Date, default=date.today)
    valid_until: Mapped[date | None] = mapped_column(Date)
    term_months: Mapped[int] = mapped_column(Integer, default=12)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    terms_text: Mapped[str | None] = mapped_column(Text)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    opportunity_name: Mapped[str | None] = mapped_column(String(255))
    sales_owner: Mapped[str | None] = mapped_column(String(128))
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    place_of_supply_state: Mapped[str | None] = mapped_column(String(64))
    place_of_supply_code: Mapped[str | None] = mapped_column(String(8))
    tax_mode: Mapped[str] = mapped_column(String(16), default="auto")
    # auto | cgst_sgst | igst | export_zero
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    party: Mapped[Party] = relationship(back_populates="quotes")
    lines: Mapped[list[QuoteLine]] = relationship(
        back_populates="quote", cascade="all, delete-orphan"
    )
    invoices: Mapped[list[Invoice]] = relationship(back_populates="quote")


class QuoteLine(Base):
    __tablename__ = "quote_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quotes.id"), nullable=False)
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_items.id"))
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("18.00"))
    hsn_sac: Mapped[str | None] = mapped_column(String(16))
    vendor_name: Mapped[str | None] = mapped_column(String(128))
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    line_taxable: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    line_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, default=10)

    quote: Mapped[Quote] = relationship(back_populates="lines")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    invoice_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parties.id"), nullable=False)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("quotes.id"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | issued | paid | partially_paid | void | credited
    invoice_type: Mapped[str] = mapped_column(String(32), default="tax_invoice")
    # tax_invoice | credit_note | proforma
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    issue_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date)
    place_of_supply_state: Mapped[str | None] = mapped_column(String(64))
    place_of_supply_code: Mapped[str | None] = mapped_column(String(8))
    tax_mode: Mapped[str] = mapped_column(String(16), default="igst")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    party: Mapped[Party] = relationship(back_populates="invoices")
    quote: Mapped[Quote | None] = relationship(back_populates="invoices")
    lines: Mapped[list[InvoiceLine]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("18.00"))
    hsn_sac: Mapped[str | None] = mapped_column(String(16))
    vendor_name: Mapped[str | None] = mapped_column(String(128))
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    line_taxable: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    line_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, default=10)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class SequenceCounter(Base):
    __tablename__ = "sequence_counters"
    __table_args__ = (UniqueConstraint("name", "year", name="uq_seq_name_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, default=date.today)
    method: Mapped[str] = mapped_column(String(64), default="bank_transfer")
    # bank_transfer | upi | cheque | card | cash | other
    reference: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class CompanyProfile(Base):
    """Single-row seller profile (Tally company masters equivalent)."""

    __tablename__ = "company_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(20))
    pan: Mapped[str | None] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(64), default="Maharashtra")
    state_code: Mapped[str] = mapped_column(String(8), default="27")
    address: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    website: Mapped[str | None] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(128))
    bank_account: Mapped[str | None] = mapped_column(String(64))
    bank_ifsc: Mapped[str | None] = mapped_column(String(32))
    bank_branch: Mapped[str | None] = mapped_column(String(128))
    upi_id: Mapped[str | None] = mapped_column(String(128))
    default_terms: Mapped[str | None] = mapped_column(Text)
    invoice_footer: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    lut_filed: Mapped[bool] = mapped_column(Boolean, default=False)
    quote_validity_days: Mapped[int] = mapped_column(Integer, default=30)
    discount_approval_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("15.00")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Contact(Base):
    """A person at a customer. A company (party) can have several."""

    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parties.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    party: Mapped[Party] = relationship()


class Lead(Base):
    """First contact, before there is a deal. Source and interest are free text."""

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lead_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    contact_title: Mapped[str | None] = mapped_column(String(128))
    source: Mapped[str | None] = mapped_column(String(128))
    interest: Mapped[str | None] = mapped_column(Text)
    estimated_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(32), default="new")
    # new | contacted | qualified | unqualified | converted
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("salespeople.id"))
    owner: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parties.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Opportunity(Base):
    """One customer requirement / deal. Quotes and invoices hang off this."""

    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    opportunity_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parties.id"), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    stage: Mapped[str] = mapped_column(String(32), default="prospecting")
    # prospecting | needs_analysis | proposal | negotiation | closed_won | closed_lost
    source: Mapped[str | None] = mapped_column(String(128))
    supplier: Mapped[str | None] = mapped_column(String(128))
    deal_reg_number: Mapped[str | None] = mapped_column(String(128))
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("salespeople.id"))
    owner: Mapped[str | None] = mapped_column(String(128))
    requirement: Mapped[str | None] = mapped_column(Text)
    amount_expected: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    close_date: Mapped[date | None] = mapped_column(Date)
    probability: Mapped[int] = mapped_column(Integer, default=10)
    next_step: Mapped[str | None] = mapped_column(String(255))
    lost_reason: Mapped[str | None] = mapped_column(Text)
    customer_po: Mapped[str | None] = mapped_column(String(128))
    supplier_order_ref: Mapped[str | None] = mapped_column(String(128))
    fulfillment_status: Mapped[str] = mapped_column(String(32), default="none")
    # none | customer_po | ordered_from_supplier | delivered | invoiced | collected
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    party: Mapped[Party] = relationship()


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parties.id"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"))
    kind: Mapped[str] = mapped_column(String(32), default="note")
    # note | call | email | meeting | task
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    due_on: Mapped[date | None] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Salesperson(Base):
    """Someone on our sales team. A lead or a deal is assigned to one of them."""

    __tablename__ = "salespeople"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # bdc | bde | manager
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplierPrice(Base):
    """A price our sales person took from an OEM or a distributor for one requirement."""

    __tablename__ = "supplier_prices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_kind: Mapped[str] = mapped_column(String(32), default="oem")
    # oem | distributor
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("1"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    sell_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("18.00"))
    quote_ref: Mapped[str | None] = mapped_column(String(128))
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="requested")
    # requested | received | chosen | declined
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
