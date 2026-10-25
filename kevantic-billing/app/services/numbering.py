from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import SequenceCounter


def next_number(db: Session, prefix: str, name: str) -> str:
    """Tally-like voucher: KEV/QT/2026/0001 or KEV/INV/2026/0001."""
    year = date.today().year
    row = (
        db.query(SequenceCounter)
        .filter(SequenceCounter.name == name, SequenceCounter.year == year)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        row = SequenceCounter(name=name, year=year, last_value=0)
        db.add(row)
        db.flush()
    row.last_value += 1
    db.flush()
    return f"{prefix}/{year}/{row.last_value:04d}"


def next_quote_number(db: Session) -> str:
    return next_number(db, "KEV/QT", "quote")


def next_invoice_number(db: Session) -> str:
    return next_number(db, "KEV/INV", "invoice")


def next_credit_note_number(db: Session) -> str:
    return next_number(db, "KEV/CN", "credit_note")
