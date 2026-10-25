from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.db import get_db
from app.models import Party, Quote
from app.schemas import QuoteCreate, QuoteOut
from app.services import quote_engine
from app.services.pdf import render_document_pdf

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("", response_model=list[QuoteOut])
def list_quotes(
    db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> list[Quote]:
    return (
        db.query(Quote)
        .options(joinedload(Quote.lines))
        .order_by(Quote.created_at.desc())
        .all()
    )


@router.post("", response_model=QuoteOut, status_code=201)
def create_quote(
    body: QuoteCreate, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Quote:
    party = db.get(Party, body.party_id)
    if not party:
        raise HTTPException(404, "Party not found")
    if not body.lines:
        raise HTTPException(400, "At least one line required")
    try:
        quote = quote_engine.build_quote(
            db,
            party=party,
            line_specs=[ln.model_dump() for ln in body.lines],
            term_months=body.term_months,
            discount_percent=body.discount_percent,
            notes=body.notes,
            tax_mode_forced=body.tax_mode,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return (
        db.query(Quote)
        .options(joinedload(Quote.lines))
        .filter(Quote.id == quote.id)
        .one()
    )


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Quote:
    quote = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote_id)
        .one_or_none()
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    return quote


@router.post("/{quote_id}/send", response_model=QuoteOut)
def mark_sent(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Quote:
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    quote.status = "sent"
    db.commit()
    return (
        db.query(Quote)
        .options(joinedload(Quote.lines))
        .filter(Quote.id == quote_id)
        .one()
    )


@router.post("/{quote_id}/accept", response_model=QuoteOut)
def mark_accepted(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Quote:
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    quote.status = "accepted"
    db.commit()
    return (
        db.query(Quote)
        .options(joinedload(Quote.lines))
        .filter(Quote.id == quote_id)
        .one()
    )


@router.get("/{quote_id}/pdf")
def quote_pdf(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Response:
    quote = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote_id)
        .one_or_none()
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    party = quote.party
    pdf = render_document_pdf(
        doc_title="COMMERCIAL QUOTATION",
        doc_number=quote.quote_number,
        party_name=party.legal_name,
        party_address=party.billing_address,
        party_gstin=party.gstin,
        party_state=party.state,
        issue_date=str(quote.issue_date),
        due_or_valid=f"Valid until: {quote.valid_until}",
        tax_mode=quote.tax_mode,
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
            for ln in quote.lines
        ],
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        taxable_amount=quote.taxable_amount,
        cgst_amount=quote.cgst_amount,
        sgst_amount=quote.sgst_amount,
        igst_amount=quote.igst_amount,
        total_amount=quote.total_amount,
        currency=quote.currency,
        notes=quote.notes,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{quote.quote_number.replace("/", "-")}.pdf"'
        },
    )
