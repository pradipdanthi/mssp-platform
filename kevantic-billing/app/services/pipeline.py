"""Keep Opportunity stage in sync with quote acceptance, invoice, and payment."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Opportunity


def mark_closed_won(db: Session, opportunity_id) -> None:
    """Quote accepted or tax invoice raised → deal won."""
    if not opportunity_id:
        return
    opp = db.get(Opportunity, opportunity_id)
    if not opp or opp.stage == "closed_lost":
        return
    opp.stage = "closed_won"
    opp.probability = 100


def mark_invoiced(db: Session, opportunity_id) -> None:
    if not opportunity_id:
        return
    opp = db.get(Opportunity, opportunity_id)
    if not opp or opp.stage == "closed_lost":
        return
    opp.stage = "closed_won"
    opp.probability = 100
    opp.fulfillment_status = "invoiced"


def mark_collected(db: Session, opportunity_id) -> None:
    if not opportunity_id:
        return
    opp = db.get(Opportunity, opportunity_id)
    if not opp or opp.stage == "closed_lost":
        return
    opp.stage = "closed_won"
    opp.probability = 100
    opp.fulfillment_status = "collected"
