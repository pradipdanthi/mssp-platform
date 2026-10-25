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
