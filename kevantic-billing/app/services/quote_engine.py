from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CatalogItem, Invoice, InvoiceLine, Party, Quote, QuoteLine
from app.services import numbering
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
    tax_mode_forced: str = "auto",
    status: str = "draft",
) -> Quote:
    settings = get_settings()
    tax_mode = resolve_tax_mode(
        company_state_code=settings.company_state_code,
        party_state_code=party.state_code,
        is_export=bool(party.is_export),
        lut_filed=settings.lut_filed,
        forced=tax_mode_forced,
    )

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
        unit = Decimal(str(spec.get("unit_price") if spec.get("unit_price") is not None else (item.list_price if item else 0)))
        # Subscription list price is monthly — extend by term
        billing_model = item.billing_model if item else spec.get("billing_model", "one_time")
        unit = money(unit * _term_multiplier(billing_model, term_months))
        gst = Decimal(str(spec.get("gst_rate") if spec.get("gst_rate") is not None else (item.gst_rate if item else 18)))
        disc = Decimal(str(spec.get("discount_percent") or 0))
        hsn = spec.get("hsn_sac") or (item.hsn_sac if item else None)

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
            }
        )

    totals = calc_document(
        prepared, doc_discount_percent=Decimal(str(discount_percent)), tax_mode=tax_mode
    )

    quote = Quote(
        quote_number=numbering.next_quote_number(db),
        party_id=party.id,
        status=status,
        currency=party.currency or settings.default_currency,
        issue_date=date.today(),
        valid_until=date.today() + timedelta(days=settings.quote_validity_days),
        term_months=term_months,
        discount_percent=money(discount_percent),
        notes=notes,
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


def accept_quote_to_invoice(db: Session, quote: Quote) -> Invoice:
    if quote.status not in ("draft", "sent", "accepted"):
        raise ValueError(f"Cannot invoice quote in status {quote.status}")

    party = quote.party
    settings = get_settings()
    due = date.today() + timedelta(days=party.payment_terms_days or 15)

    inv = Invoice(
        invoice_number=numbering.next_invoice_number(db),
        party_id=party.id,
        quote_id=quote.id,
        status="issued",
        invoice_type="tax_invoice",
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
        or f"Converted from quote {quote.quote_number}. Seller: {settings.company_name}",
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
                line_subtotal=ql.line_subtotal,
                line_taxable=ql.line_taxable,
                line_tax=ql.line_tax,
                line_total=ql.line_total,
                sort_order=ql.sort_order,
            )
        )
    quote.status = "invoiced"
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
