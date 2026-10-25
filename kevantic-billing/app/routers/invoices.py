from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.db import get_db
from app.models import Invoice, Quote
from app.schemas import InvoiceOut, MarkPaidIn, PaymentOut
from app.services import quote_engine
from app.services.company import get_or_create_profile
from app.services.pdf import render_document_pdf
from app.services.tax import money

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def _enrich(inv: Invoice) -> InvoiceOut:
    data = InvoiceOut.model_validate(inv)
    data.balance_due = money(
        Decimal(str(inv.total_amount)) - Decimal(str(inv.amount_paid or 0))
    )
    if inv.party:
        data.party_name = inv.party.legal_name
    return data


@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> list[InvoiceOut]:
    rows = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.lines),
            joinedload(Invoice.party),
            joinedload(Invoice.payments),
        )
        .order_by(Invoice.created_at.desc())
        .all()
    )
    return [_enrich(i) for i in rows]


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> InvoiceOut:
    inv = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.lines),
            joinedload(Invoice.party),
            joinedload(Invoice.payments),
        )
        .filter(Invoice.id == invoice_id)
        .one_or_none()
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return _enrich(inv)


@router.post("/from-quote/{quote_id}", response_model=InvoiceOut, status_code=201)
def invoice_from_quote(
    quote_id: UUID,
    invoice_type: str = Query(default="tax_invoice"),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> InvoiceOut:
    if invoice_type not in ("tax_invoice", "proforma"):
        raise HTTPException(400, "invoice_type must be tax_invoice or proforma")
    quote = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote_id)
        .one_or_none()
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    try:
        inv = quote_engine.accept_quote_to_invoice(db, quote, invoice_type=invoice_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _load(db, inv.id)


@router.post("/{invoice_id}/credit-note", response_model=InvoiceOut, status_code=201)
def credit_note(
    invoice_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> InvoiceOut:
    inv = (
        db.query(Invoice)
        .options(joinedload(Invoice.lines))
        .filter(Invoice.id == invoice_id)
        .one_or_none()
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    try:
        cn = quote_engine.create_credit_note(db, inv)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _load(db, cn.id)


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceOut)
def mark_paid(
    invoice_id: UUID,
    body: MarkPaidIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> InvoiceOut:
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    pay = money(body.amount if body.amount is not None else (
        Decimal(str(inv.total_amount)) - Decimal(str(inv.amount_paid or 0))
    ))
    try:
        quote_engine.record_payment(
            db,
            inv,
            amount=pay,
            method=body.method,
            reference=body.reference,
            notes=body.notes,
            payment_date=body.payment_date,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _load(db, invoice_id)


@router.get("/{invoice_id}/payments", response_model=list[PaymentOut])
def list_payments(
    invoice_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> list:
    inv = (
        db.query(Invoice)
        .options(joinedload(Invoice.payments))
        .filter(Invoice.id == invoice_id)
        .one_or_none()
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return inv.payments


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
def void_invoice(
    invoice_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> InvoiceOut:
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if Decimal(str(inv.amount_paid or 0)) > 0:
        raise HTTPException(400, "Cannot void an invoice with payments — issue credit note")
    inv.status = "void"
    db.commit()
    return _load(db, invoice_id)


def _load(db: Session, invoice_id: UUID) -> InvoiceOut:
    inv = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.lines),
            joinedload(Invoice.party),
            joinedload(Invoice.payments),
        )
        .filter(Invoice.id == invoice_id)
        .one()
    )
    return _enrich(inv)


@router.get("/{invoice_id}/pdf")
def invoice_pdf(
    invoice_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Response:
    inv = (
        db.query(Invoice)
        .options(joinedload(Invoice.lines), joinedload(Invoice.party))
        .filter(Invoice.id == invoice_id)
        .one_or_none()
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    party = inv.party
    profile = get_or_create_profile(db)
    title = {
        "tax_invoice": "TAX INVOICE",
        "credit_note": "CREDIT NOTE",
        "proforma": "PROFORMA INVOICE",
    }.get(inv.invoice_type, inv.invoice_type.upper())
    pdf = render_document_pdf(
        doc_title=title,
        doc_number=inv.invoice_number,
        party_name=party.legal_name,
        party_address=party.billing_address,
        party_gstin=party.gstin,
        party_state=party.state,
        issue_date=str(inv.issue_date),
        due_or_valid=f"Due date: {inv.due_date}" if inv.due_date else None,
        tax_mode=inv.tax_mode,
        lines=[
            {
                "sku": ln.sku,
                "description": ln.description,
                "hsn_sac": ln.hsn_sac,
                "quantity": ln.quantity,
                "unit_price": ln.unit_price,
                "line_taxable": ln.line_taxable,
                "line_tax": ln.line_tax,
                "line_total": ln.line_total,
            }
            for ln in inv.lines
        ],
        subtotal=inv.subtotal,
        discount_amount=inv.discount_amount,
        taxable_amount=inv.taxable_amount,
        cgst_amount=inv.cgst_amount,
        sgst_amount=inv.sgst_amount,
        igst_amount=inv.igst_amount,
        total_amount=inv.total_amount,
        currency=inv.currency,
        notes=inv.notes,
        terms=profile.default_terms,
        company=profile,
        amount_paid=inv.amount_paid,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{inv.invoice_number.replace("/", "-")}.pdf"'
        },
    )
