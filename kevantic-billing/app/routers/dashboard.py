from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import Invoice, Party, Quote
from app.services.tax import money

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> dict:
    today = date.today()
    month_start = today.replace(day=1)

    open_quotes = (
        db.query(func.count(Quote.id))
        .filter(Quote.status.in_(("draft", "sent", "accepted", "pending_approval")))
        .scalar()
        or 0
    )
    quotes_value = (
        db.query(func.coalesce(func.sum(Quote.total_amount), 0))
        .filter(Quote.status.in_(("draft", "sent", "accepted", "pending_approval")))
        .scalar()
    )
    issued = (
        db.query(Invoice)
        .filter(Invoice.invoice_type == "tax_invoice")
        .filter(Invoice.status.in_(("issued", "partially_paid", "paid")))
        .all()
    )
    outstanding = money(
        sum(
            (
                Decimal(str(i.total_amount)) - Decimal(str(i.amount_paid or 0))
                for i in issued
                if i.status != "paid"
            ),
            Decimal("0"),
        )
    )
    overdue = []
    for i in issued:
        bal = money(Decimal(str(i.total_amount)) - Decimal(str(i.amount_paid or 0)))
        if bal > 0 and i.due_date and i.due_date < today and i.status != "paid":
            overdue.append(
                {
                    "id": str(i.id),
                    "invoice_number": i.invoice_number,
                    "due_date": str(i.due_date),
                    "balance": float(bal),
                    "days_overdue": (today - i.due_date).days,
                }
            )
    overdue.sort(key=lambda x: -x["days_overdue"])

    collected_mtd = (
        db.query(func.coalesce(func.sum(Invoice.amount_paid), 0))
        .filter(Invoice.invoice_type == "tax_invoice")
        .filter(Invoice.issue_date >= month_start)
        .scalar()
    )
    invoiced_mtd = (
        db.query(func.coalesce(func.sum(Invoice.total_amount), 0))
        .filter(Invoice.invoice_type == "tax_invoice")
        .filter(Invoice.issue_date >= month_start)
        .scalar()
    )

    # GST liability from tax invoices issued this month (not credit notes)
    gst_rows = (
        db.query(
            func.coalesce(func.sum(Invoice.cgst_amount), 0),
            func.coalesce(func.sum(Invoice.sgst_amount), 0),
            func.coalesce(func.sum(Invoice.igst_amount), 0),
            func.coalesce(func.sum(Invoice.taxable_amount), 0),
        )
        .filter(Invoice.invoice_type == "tax_invoice")
        .filter(Invoice.status != "void")
        .filter(Invoice.issue_date >= month_start)
        .one()
    )
    cn_tax = (
        db.query(func.coalesce(func.sum(Invoice.igst_amount + Invoice.cgst_amount + Invoice.sgst_amount), 0))
        .filter(Invoice.invoice_type == "credit_note")
        .filter(Invoice.issue_date >= month_start)
        .scalar()
    )

    # Aging buckets
    buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0}
    for i in issued:
        bal = float(money(Decimal(str(i.total_amount)) - Decimal(str(i.amount_paid or 0))))
        if bal <= 0 or i.status == "paid":
            continue
        if not i.due_date or i.due_date >= today:
            buckets["current"] += bal
            continue
        days = (today - i.due_date).days
        if days <= 30:
            buckets["1_30"] += bal
        elif days <= 60:
            buckets["31_60"] += bal
        elif days <= 90:
            buckets["61_90"] += bal
        else:
            buckets["90_plus"] += bal

    recent_quotes = (
        db.query(Quote).order_by(Quote.created_at.desc()).limit(5).all()
    )
    recent_invoices = (
        db.query(Invoice).order_by(Invoice.created_at.desc()).limit(5).all()
    )
    party_count = db.query(func.count(Party.id)).scalar() or 0
    pending_approval = (
        db.query(func.count(Quote.id)).filter(Quote.status == "pending_approval").scalar()
        or 0
    )

    expiring_soon = (
        db.query(Quote)
        .filter(Quote.status.in_(("draft", "sent", "accepted", "pending_approval")))
        .filter(Quote.valid_until != None)  # noqa: E711
        .filter(Quote.valid_until <= today + timedelta(days=7))
        .filter(Quote.valid_until >= today)
        .all()
    )

    return {
        "kpis": {
            "open_quotes": open_quotes,
            "open_quotes_value": float(money(quotes_value)),
            "outstanding_ar": float(outstanding),
            "overdue_count": len(overdue),
            "collected_mtd": float(money(collected_mtd)),
            "invoiced_mtd": float(money(invoiced_mtd)),
            "parties": party_count,
            "pending_approval": pending_approval,
        },
        "gst_mtd": {
            "taxable": float(money(gst_rows[3])),
            "cgst": float(money(gst_rows[0])),
            "sgst": float(money(gst_rows[1])),
            "igst": float(money(gst_rows[2])),
            "credit_note_tax": float(money(cn_tax)),
        },
        "aging": buckets,
        "overdue": overdue[:10],
        "expiring_quotes": [
            {
                "id": str(q.id),
                "quote_number": q.quote_number,
                "valid_until": str(q.valid_until),
                "total_amount": float(q.total_amount),
            }
            for q in expiring_soon
        ],
        "recent_quotes": [
            {
                "id": str(q.id),
                "quote_number": q.quote_number,
                "status": q.status,
                "total_amount": float(q.total_amount),
                "currency": q.currency,
            }
            for q in recent_quotes
        ],
        "recent_invoices": [
            {
                "id": str(i.id),
                "invoice_number": i.invoice_number,
                "status": i.status,
                "invoice_type": i.invoice_type,
                "total_amount": float(i.total_amount),
                "amount_paid": float(i.amount_paid or 0),
                "currency": i.currency,
            }
            for i in recent_invoices
        ],
    }
