from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.db import get_db
from app.models import Party, Quote
from app.schemas import QuoteCreate, QuoteOut
from app.services import quote_engine
from app.services.company import get_or_create_profile
from app.services.pdf import render_document_pdf

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


def _enrich(q: Quote) -> QuoteOut:
    data = QuoteOut.model_validate(q)
    if q.party:
        data.party_name = q.party.legal_name
    return data


@router.get("", response_model=list[QuoteOut])
def list_quotes(
    db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> list[QuoteOut]:
    rows = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .order_by(Quote.created_at.desc())
        .all()
    )
    return [_enrich(q) for q in rows]


@router.post("", response_model=QuoteOut, status_code=201)
def create_quote(
    body: QuoteCreate, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> QuoteOut:
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
            internal_notes=body.internal_notes,
            terms_text=body.terms_text,
            opportunity_name=body.opportunity_name,
            sales_owner=body.sales_owner,
            opportunity_id=body.opportunity_id,
            tax_mode_forced=body.tax_mode,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    q = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote.id)
        .one()
    )
    return _enrich(q)


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> QuoteOut:
    quote = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote_id)
        .one_or_none()
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    return _enrich(quote)


@router.post("/{quote_id}/send", response_model=QuoteOut)
def mark_sent(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> QuoteOut:
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    if quote.status == "pending_approval":
        raise HTTPException(400, "Approve discount before sending")
    quote.status = "sent"
    db.commit()
    return _load(db, quote_id)


@router.post("/{quote_id}/accept", response_model=QuoteOut)
def mark_accepted(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> QuoteOut:
    quote = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote_id)
        .one_or_none()
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    quote.status = "accepted"
    from app.services.pipeline import mark_closed_won

    mark_closed_won(db, quote.opportunity_id)
    # Lead-to-cash: accepted quote with an Opportunity becomes a tax invoice
    if quote.opportunity_id and quote.status != "invoiced":
        try:
            quote_engine.accept_quote_to_invoice(db, quote, invoice_type="tax_invoice")
        except ValueError:
            db.commit()
            return _load(db, quote_id)
        return _load(db, quote_id)
    db.commit()
    return _load(db, quote_id)


@router.post("/{quote_id}/decline", response_model=QuoteOut)
def mark_declined(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> QuoteOut:
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    quote.status = "declined"
    db.commit()
    return _load(db, quote_id)


@router.post("/{quote_id}/approve", response_model=QuoteOut)
def approve_discount(
    quote_id: UUID,
    db: Session = Depends(get_db),
    user: str = Depends(require_admin),
) -> QuoteOut:
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    quote.approved_by = user
    quote.requires_approval = False
    if quote.status == "pending_approval":
        quote.status = "draft"
    db.commit()
    return _load(db, quote_id)


@router.post("/{quote_id}/duplicate", response_model=QuoteOut, status_code=201)
def duplicate(
    quote_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> QuoteOut:
    source = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote_id)
        .one_or_none()
    )
    if not source:
        raise HTTPException(404, "Quote not found")
    try:
        q = quote_engine.duplicate_quote(db, source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _load(db, q.id)


def _load(db: Session, quote_id: UUID) -> QuoteOut:
    q = (
        db.query(Quote)
        .options(joinedload(Quote.lines), joinedload(Quote.party))
        .filter(Quote.id == quote_id)
        .one()
    )
    return _enrich(q)


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
    profile = get_or_create_profile(db)
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
                "vendor_name": ln.vendor_name,
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
        terms=quote.terms_text,
        company=profile,
        opportunity=quote.opportunity_name,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{quote.quote_number.replace("/", "-")}.pdf"'
        },
    )
