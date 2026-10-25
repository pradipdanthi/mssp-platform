from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.db import get_db
from app.models import Invoice, Quote
from app.schemas import InvoiceOut, MarkPaidIn
from app.services import quote_engine
from app.services.pdf import render_document_pdf
from app.services.tax import money

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> list[Invoice]:
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.lines))
        .order_by(Invoice.created_at.desc())
        .all()
    )


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Invoice:
    inv = (
        db.query(Invoice)
        .options(joinedload(Invoice.lines), joinedload(Invoice.party))
        .filter(Invoice.id == invoice_id)
        .one_or_none()
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.post("/from-quote/{quote_id}", response_model=InvoiceOut, status_code=201)
def invoice_from_quote(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Invoice:
    quote = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote_id)
        .one_or_none()
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    try:
        inv = quote_engine.accept_quote_to_invoice(db, quote)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.lines))
        .filter(Invoice.id == inv.id)
        .one()
    )


@router.post("/{invoice_id}/credit-note", response_model=InvoiceOut, status_code=201)
def credit_note(
    invoice_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Invoice:
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
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.lines))
        .filter(Invoice.id == cn.id)
        .one()
    )


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceOut)
def mark_paid(
    invoice_id: UUID,
    body: MarkPaidIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    pay = money(body.amount if body.amount is not None else inv.total_amount)
    inv.amount_paid = money(Decimal(str(inv.amount_paid)) + pay)
    if inv.amount_paid >= inv.total_amount:
        inv.status = "paid"
    else:
        inv.status = "partially_paid"
    db.commit()
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.lines))
        .filter(Invoice.id == invoice_id)
        .one()
    )


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
    title = (
        "TAX INVOICE"
        if inv.invoice_type == "tax_invoice"
        else inv.invoice_type.replace("_", " ").upper()
    )
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
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{inv.invoice_number.replace("/", "-")}.pdf"'
        },
    )
