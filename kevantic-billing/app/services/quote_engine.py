from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    CatalogItem,
    Invoice,
    InvoiceLine,
    Opportunity,
    Party,
    Payment,
    Quote,
    QuoteLine,
)
from app.services import numbering
from app.services.company import get_or_create_profile
from app.services.pipeline import mark_collected, mark_invoiced
from app.services.tax import calc_document, money, resolve_tax_mode


def _term_multiplier(billing_model: str, term_months: int) -> Decimal:
    if billing_model == "subscription":
        return Decimal(str(max(term_months, 1)))
    return Decimal("1")


def build_quote(
    db: Session,
    *,
    party: Party,
    line_specs: list[dict],
    term_months: int = 12,
    discount_percent: Decimal = Decimal("0"),
    notes: str | None = None,
    internal_notes: str | None = None,
    terms_text: str | None = None,
    opportunity_name: str | None = None,
    sales_owner: str | None = None,
    opportunity_id: UUID | None = None,
    tax_mode_forced: str = "auto",
    status: str = "draft",
) -> Quote:
    profile = get_or_create_profile(db)
    tax_mode = resolve_tax_mode(
        company_state_code=profile.state_code,
        party_state_code=party.state_code,
        is_export=bool(party.is_export),
        lut_filed=bool(profile.lut_filed),
        forced=tax_mode_forced,
    )

    linked: Opportunity | None = None
    if opportunity_id:
        linked = db.get(Opportunity, opportunity_id)
        if linked is None or linked.party_id != party.id:
            raise ValueError("Deal does not belong to this customer")
        opportunity_name = opportunity_name or linked.name
        sales_owner = sales_owner or linked.owner
        if linked.stage in ("prospecting", "needs_analysis", "qualification", "discovery", "assigned", "working", "supplier_price"):
            linked.stage = "proposal"
            linked.probability = 50

    prepared: list[dict] = []
    line_meta: list[dict] = []
    for spec in line_specs:
        item: CatalogItem | None = None
        if spec.get("catalog_item_id"):
            item = db.get(CatalogItem, UUID(str(spec["catalog_item_id"])))
        elif spec.get("sku"):
            item = db.query(CatalogItem).filter(CatalogItem.sku == spec["sku"]).one_or_none()
        if item is None and not spec.get("description"):
            raise ValueError(f"Unknown catalog item: {spec}")

        sku = (item.sku if item else spec.get("sku")) or "CUSTOM"
        desc = spec.get("description") or (item.name if item else "Custom line")
        qty = Decimal(str(spec.get("quantity") or (item.min_qty if item else 1)))
        unit = Decimal(
            str(
                spec.get("unit_price")
                if spec.get("unit_price") is not None
                else (item.list_price if item else 0)
            )
        )
        billing_model = item.billing_model if item else spec.get("billing_model", "one_time")
        unit = money(unit * _term_multiplier(billing_model, term_months))
        gst = Decimal(
            str(
                spec.get("gst_rate")
                if spec.get("gst_rate") is not None
                else (item.gst_rate if item else 18)
            )
        )
        disc = Decimal(str(spec.get("discount_percent") or 0))
        hsn = spec.get("hsn_sac") or (item.hsn_sac if item else None)
        vendor = (spec.get("vendor_name") or (item.vendor_name if item else None) or "").strip() or None

        prepared.append(
            {
                "quantity": qty,
                "unit_price": unit,
                "discount_percent": disc,
                "gst_rate": gst,
            }
        )
        line_meta.append(
            {
                "catalog_item_id": item.id if item else None,
                "sku": sku,
                "description": desc
                + (f" ({term_months} mo)" if billing_model == "subscription" else ""),
                "quantity": qty,
                "unit_price": unit,
                "discount_percent": disc,
                "gst_rate": gst,
                "hsn_sac": hsn,
                "vendor_name": vendor,
            }
        )

    totals = calc_document(
        prepared, doc_discount_percent=Decimal(str(discount_percent)), tax_mode=tax_mode
    )
    disc_pct = money(discount_percent)
    needs_approval = disc_pct >= money(profile.discount_approval_threshold)

    quote = Quote(
        quote_number=numbering.next_quote_number(db),
        party_id=party.id,
        status="pending_approval" if needs_approval and status == "draft" else status,
        currency=party.currency or profile.currency,
        issue_date=date.today(),
        valid_until=date.today() + timedelta(days=profile.quote_validity_days),
        term_months=term_months,
        discount_percent=disc_pct,
        notes=notes,
        internal_notes=internal_notes,
        terms_text=terms_text or profile.default_terms,
        opportunity_id=linked.id if linked else None,
        opportunity_name=opportunity_name,
        sales_owner=sales_owner,
        requires_approval=needs_approval,
        place_of_supply_state=party.state,
        place_of_supply_code=party.state_code,
        tax_mode=tax_mode,
        subtotal=totals.subtotal,
        discount_amount=totals.discount_amount,
        taxable_amount=totals.taxable_amount,
        cgst_amount=totals.cgst_amount,
        sgst_amount=totals.sgst_amount,
        igst_amount=totals.igst_amount,
        total_amount=totals.total_amount,
    )
    db.add(quote)
    db.flush()

    for i, (meta, lr) in enumerate(zip(line_meta, totals.lines)):
        db.add(
            QuoteLine(
                quote_id=quote.id,
                catalog_item_id=meta["catalog_item_id"],
                sku=meta["sku"],
                description=meta["description"],
                quantity=meta["quantity"],
                unit_price=meta["unit_price"],
                discount_percent=meta["discount_percent"],
                gst_rate=meta["gst_rate"],
                hsn_sac=meta["hsn_sac"],
                vendor_name=meta.get("vendor_name"),
                line_subtotal=lr.line_subtotal,
                line_taxable=lr.line_taxable,
                line_tax=lr.line_tax,
                line_total=lr.line_total,
                sort_order=(i + 1) * 10,
            )
        )
    db.commit()
    db.refresh(quote)
    return quote


def duplicate_quote(db: Session, source: Quote) -> Quote:
    party = source.party
    specs = [
        {
            "sku": ln.sku,
            "description": ln.description.split(" (")[0],
            "quantity": ln.quantity,
            # unit_price already term-extended — pass as one_time so we don't multiply again
            "unit_price": ln.unit_price,
            "discount_percent": ln.discount_percent,
            "gst_rate": ln.gst_rate,
            "hsn_sac": ln.hsn_sac,
            "vendor_name": ln.vendor_name,
            "billing_model": "one_time",
        }
        for ln in sorted(source.lines, key=lambda x: x.sort_order)
    ]
    return build_quote(
        db,
        party=party,
        line_specs=specs,
        term_months=1,  # prices already term-extended on source lines
        discount_percent=source.discount_percent,
        notes=source.notes,
        internal_notes=source.internal_notes,
        terms_text=source.terms_text,
        opportunity_name=source.opportunity_name,
        sales_owner=source.sales_owner,
        opportunity_id=source.opportunity_id,
        tax_mode_forced=source.tax_mode,
        status="draft",
    )


def accept_quote_to_invoice(
    db: Session, quote: Quote, *, invoice_type: str = "tax_invoice"
) -> Invoice:
    if quote.status in ("declined", "expired"):
        raise ValueError(f"Cannot invoice quote in status {quote.status}")
    if quote.requires_approval and not quote.approved_by and quote.status == "pending_approval":
        raise ValueError("Quote requires discount approval before invoicing")

    party = quote.party
    profile = get_or_create_profile(db)
    due = date.today() + timedelta(days=party.payment_terms_days or 15)

    if invoice_type == "proforma":
        inv_number = numbering.next_number(db, "KEV/PF", "proforma")
        status = "issued"
    else:
        inv_number = numbering.next_invoice_number(db)
        status = "issued"

    inv = Invoice(
        invoice_number=inv_number,
        party_id=party.id,
        quote_id=quote.id,
        opportunity_id=quote.opportunity_id,
        status=status,
        invoice_type=invoice_type,
        currency=quote.currency,
        issue_date=date.today(),
        due_date=due,
        place_of_supply_state=quote.place_of_supply_state,
        place_of_supply_code=quote.place_of_supply_code,
        tax_mode=quote.tax_mode,
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        taxable_amount=quote.taxable_amount,
        cgst_amount=quote.cgst_amount,
        sgst_amount=quote.sgst_amount,
        igst_amount=quote.igst_amount,
        total_amount=quote.total_amount,
        notes=quote.notes
        or f"From quote {quote.quote_number}. Seller: {profile.legal_name}",
    )
    db.add(inv)
    db.flush()
    for ql in sorted(quote.lines, key=lambda x: x.sort_order):
        db.add(
            InvoiceLine(
                invoice_id=inv.id,
                sku=ql.sku,
                description=ql.description,
                quantity=ql.quantity,
                unit_price=ql.unit_price,
                discount_percent=ql.discount_percent,
                gst_rate=ql.gst_rate,
                hsn_sac=ql.hsn_sac,
                vendor_name=ql.vendor_name,
                line_subtotal=ql.line_subtotal,
                line_taxable=ql.line_taxable,
                line_tax=ql.line_tax,
                line_total=ql.line_total,
                sort_order=ql.sort_order,
            )
        )
    if invoice_type == "tax_invoice":
        quote.status = "invoiced"
        mark_invoiced(db, quote.opportunity_id)
    db.commit()
    db.refresh(inv)
    return inv


def create_credit_note(db: Session, invoice: Invoice, reason: str | None = None) -> Invoice:
    if invoice.invoice_type != "tax_invoice":
        raise ValueError("Credit notes only from tax invoices")
    cn = Invoice(
        invoice_number=numbering.next_credit_note_number(db),
        party_id=invoice.party_id,
        quote_id=invoice.quote_id,
        status="issued",
        invoice_type="credit_note",
        currency=invoice.currency,
        issue_date=date.today(),
        due_date=date.today(),
        place_of_supply_state=invoice.place_of_supply_state,
        place_of_supply_code=invoice.place_of_supply_code,
        tax_mode=invoice.tax_mode,
        subtotal=invoice.subtotal,
        discount_amount=invoice.discount_amount,
        taxable_amount=invoice.taxable_amount,
        cgst_amount=invoice.cgst_amount,
        sgst_amount=invoice.sgst_amount,
        igst_amount=invoice.igst_amount,
        total_amount=invoice.total_amount,
        notes=reason or f"Credit note against {invoice.invoice_number}",
    )
    db.add(cn)
    db.flush()
    for il in invoice.lines:
        db.add(
            InvoiceLine(
                invoice_id=cn.id,
                sku=il.sku,
                description=il.description,
                quantity=il.quantity,
                unit_price=il.unit_price,
                discount_percent=il.discount_percent,
                gst_rate=il.gst_rate,
                hsn_sac=il.hsn_sac,
                line_subtotal=il.line_subtotal,
                line_taxable=il.line_taxable,
                line_tax=il.line_tax,
                line_total=il.line_total,
                sort_order=il.sort_order,
            )
        )
    invoice.status = "credited"
    db.commit()
    db.refresh(cn)
    return cn


def record_payment(
    db: Session,
    invoice: Invoice,
    *,
    amount: Decimal,
    method: str = "bank_transfer",
    reference: str | None = None,
    notes: str | None = None,
    payment_date: date | None = None,
) -> Payment:
    if invoice.invoice_type == "credit_note":
        raise ValueError("Cannot record payment against a credit note")
    if invoice.status == "void":
        raise ValueError("Invoice is void")
    pay_amt = money(amount)
    if pay_amt <= 0:
        raise ValueError("Payment amount must be positive")
    payment = Payment(
        invoice_id=invoice.id,
        amount=pay_amt,
        payment_date=payment_date or date.today(),
        method=method,
        reference=reference,
        notes=notes,
    )
    db.add(payment)
    invoice.amount_paid = money(Decimal(str(invoice.amount_paid or 0)) + pay_amt)
    if invoice.amount_paid >= invoice.total_amount:
        invoice.status = "paid"
        mark_collected(db, invoice.opportunity_id)
    else:
        invoice.status = "partially_paid"
    db.commit()
    db.refresh(payment)
    return payment
