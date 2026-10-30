"""Salesforce-style CRM API around the existing quote and invoice engine.

Lead → Account (Party) + Contact + Opportunity.
Opportunity → Quote → Invoice → Payment.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.db import get_db
from app.models import (
    Activity,
    Contact,
    Invoice,
    Lead,
    Opportunity,
    Party,
    Quote,
    Salesperson,
    SupplierPrice,
)
from app.services import numbering, quote_engine

router = APIRouter(prefix="/api/crm", tags=["crm"])

LEAD_STATUS = {"new", "contacted", "qualified", "unqualified", "converted"}
# Accept older values from earlier builds
LEAD_STATUS_ALIAS = {"working": "contacted"}

STAGES = {
    "prospecting",
    "needs_analysis",
    "proposal",
    "negotiation",
    "closed_won",
    "closed_lost",
}
STAGE_ORDER = [
    "prospecting",
    "needs_analysis",
    "proposal",
    "negotiation",
    "closed_won",
    "closed_lost",
]
STAGE_PROBABILITY = {
    "prospecting": 10,
    "needs_analysis": 25,
    "proposal": 50,
    "negotiation": 75,
    "closed_won": 100,
    "closed_lost": 0,
}
STAGE_ALIAS = {
    "qualification": "prospecting",
    "assigned": "prospecting",
    "discovery": "needs_analysis",
    "working": "needs_analysis",
    "supplier_price": "needs_analysis",
    "commit": "closed_won",
    "won": "closed_won",
    "billed": "closed_won",
    "paid": "closed_won",
    "closed": "closed_won",
    "lost": "closed_lost",
}

ROLES = {"bdc": "BDC", "bde": "BDE", "manager": "Sales manager"}
PRICE_STATUS = {"requested", "received", "chosen", "declined"}
FULFILLMENT = {
    "none",
    "customer_po",
    "ordered_from_supplier",
    "delivered",
    "invoiced",
    "collected",
}
ACTIVITY_KINDS = {"note", "call", "email", "meeting", "task"}
OPEN_LEAD = {"new", "contacted", "qualified"}
OPEN_OPP = {"prospecting", "needs_analysis", "proposal", "negotiation"}


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str
    email: str | None = None
    phone: str | None = None


class PersonPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    active: bool | None = None


class LeadIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    contact_title: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    interest: str | None = None
    estimated_budget: Decimal | None = None
    status: str | None = None
    salesperson_id: UUID | None = None
    notes: str | None = None


class LeadPatch(BaseModel):
    company_name: str | None = None
    contact_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    contact_title: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    interest: str | None = None
    estimated_budget: Decimal | None = None
    status: str | None = None
    salesperson_id: UUID | None = None
    notes: str | None = None


class ConvertIn(BaseModel):
    salesperson_id: UUID | None = None
    opportunity_name: str | None = None
    amount_expected: Decimal | None = None
    close_date: date | None = None
    create_opportunity: bool = True


class OpportunityIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    party_id: UUID
    contact_id: UUID | None = None
    source: str | None = None
    salesperson_id: UUID | None = None
    requirement: str | None = None
    amount_expected: Decimal = Decimal("0")
    close_date: date | None = None
    next_step: str | None = None
    notes: str | None = None


class OpportunityPatch(BaseModel):
    name: str | None = None
    stage: str | None = None
    source: str | None = None
    supplier: str | None = None
    deal_reg_number: str | None = None
    salesperson_id: UUID | None = None
    requirement: str | None = None
    amount_expected: Decimal | None = None
    close_date: date | None = None
    probability: int | None = None
    next_step: str | None = None
    lost_reason: str | None = None
    customer_po: str | None = None
    supplier_order_ref: str | None = None
    fulfillment_status: str | None = None
    notes: str | None = None


class ActivityIn(BaseModel):
    kind: str = "note"
    subject: str = Field(min_length=1, max_length=255)
    body: str | None = None
    due_on: date | None = None
    owner: str | None = None


class SupplierPriceIn(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=255)
    supplier_kind: str = "oem"
    item_name: str = Field(min_length=1, max_length=255)
    sku: str | None = None
    quantity: Decimal = Decimal("1")
    unit_cost: Decimal = Decimal("0")
    sell_unit_price: Decimal | None = None
    gst_rate: Decimal = Decimal("18")
    quote_ref: str | None = None
    valid_until: date | None = None
    notes: str | None = None


class SupplierPricePatch(BaseModel):
    status: str | None = None
    sell_unit_price: Decimal | None = None
    unit_cost: Decimal | None = None
    quote_ref: str | None = None
    notes: str | None = None


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _set_salesperson(db: Session, row, salesperson_id: UUID | None) -> Salesperson | None:
    if salesperson_id is None:
        return None
    person = db.get(Salesperson, salesperson_id)
    if not person or not person.active:
        raise HTTPException(400, "That person is not on the active sales team")
    row.salesperson_id = person.id
    row.owner = person.name
    return person


def _normalize_lead_status(status: str) -> str:
    status = LEAD_STATUS_ALIAS.get(status, status)
    if status not in LEAD_STATUS:
        raise HTTPException(400, "Unknown lead status")
    return status


def _normalize_stage(stage: str) -> str:
    stage = STAGE_ALIAS.get(stage, stage)
    if stage not in STAGES:
        raise HTTPException(400, "Unknown opportunity stage")
    return stage


def _person_out(row: Salesperson) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "role": row.role,
        "role_label": ROLES.get(row.role, row.role),
        "email": row.email,
        "phone": row.phone,
        "active": row.active,
    }


def _lead_out(row: Lead, opp: Opportunity | None = None) -> dict:
    return {
        "id": str(row.id),
        "lead_number": row.lead_number,
        "company_name": row.company_name,
        "contact_name": row.contact_name,
        "contact_title": row.contact_title,
        "email": row.email,
        "phone": row.phone,
        "source": row.source,
        "interest": row.interest,
        "estimated_budget": float(row.estimated_budget) if row.estimated_budget is not None else None,
        "status": row.status,
        "salesperson_id": str(row.salesperson_id) if row.salesperson_id else None,
        "owner": row.owner,
        "notes": row.notes,
        "party_id": str(row.party_id) if row.party_id else None,
        "opportunity_id": str(opp.id) if opp else None,
        "opportunity_number": opp.opportunity_number if opp else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _price_out(row: SupplierPrice) -> dict:
    return {
        "id": str(row.id),
        "supplier_name": row.supplier_name,
        "supplier_kind": row.supplier_kind,
        "item_name": row.item_name,
        "sku": row.sku,
        "quantity": float(row.quantity or 0),
        "unit_cost": float(row.unit_cost or 0),
        "sell_unit_price": float(row.sell_unit_price) if row.sell_unit_price is not None else None,
        "gst_rate": float(row.gst_rate or 0),
        "quote_ref": row.quote_ref,
        "valid_until": str(row.valid_until) if row.valid_until else None,
        "status": row.status,
        "notes": row.notes,
    }


def _opp_out(row: Opportunity, party_name: str | None = None) -> dict:
    name = party_name
    if name is None and row.party:
        name = row.party.legal_name
    amount = float(row.amount_expected or 0)
    prob = int(row.probability or 0)
    return {
        "id": str(row.id),
        "opportunity_number": row.opportunity_number,
        "name": row.name,
        "party_id": str(row.party_id),
        "party_name": name,
        "account_name": name,
        "contact_id": str(row.contact_id) if row.contact_id else None,
        "lead_id": str(row.lead_id) if row.lead_id else None,
        "stage": row.stage,
        "source": row.source,
        "supplier": row.supplier,
        "deal_reg_number": row.deal_reg_number,
        "salesperson_id": str(row.salesperson_id) if row.salesperson_id else None,
        "owner": row.owner,
        "requirement": row.requirement,
        "amount_expected": amount,
        "deal_value": amount,
        "currency": row.currency,
        "close_date": str(row.close_date) if row.close_date else None,
        "probability": prob,
        "weighted_value": round(amount * prob / 100.0, 2),
        "next_step": row.next_step,
        "lost_reason": row.lost_reason,
        "customer_po": row.customer_po,
        "supplier_order_ref": row.supplier_order_ref,
        "fulfillment_status": row.fulfillment_status,
        "notes": row.notes,
    }


def _activity_out(row: Activity) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "subject": row.subject,
        "body": row.body,
        "due_on": str(row.due_on) if row.due_on else None,
        "done": row.done,
        "owner": row.owner,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _compose_contact_name(body) -> str | None:
    first = _blank(getattr(body, "first_name", None))
    last = _blank(getattr(body, "last_name", None))
    if first or last:
        return " ".join(p for p in (first, last) if p)
    return _blank(getattr(body, "contact_name", None))


def _convert_lead(
    db: Session,
    lead: Lead,
    *,
    salesperson_id: UUID | None = None,
    opportunity_name: str | None = None,
    amount_expected: Decimal | None = None,
    close_date: date | None = None,
    create_opportunity: bool = True,
) -> tuple[Lead, Opportunity | None, Party, Contact | None]:
    """Salesforce convert: Lead → Account + Contact + Opportunity."""
    if lead.status == "converted":
        raise HTTPException(400, "This lead is already converted")
    if lead.status == "unqualified":
        raise HTTPException(400, "Unqualified leads cannot be converted. Set status back to Contacted or Qualified first.")

    owner_id = salesperson_id or lead.salesperson_id
    if owner_id is None:
        raise HTTPException(400, "Assign a BDE or BDC before converting this lead")

    party = db.get(Party, lead.party_id) if lead.party_id else None
    if party is None:
        party = Party(
            legal_name=lead.company_name,
            display_name=lead.company_name,
            email=lead.email,
            phone=lead.phone,
            notes=lead.notes,
        )
        db.add(party)
        db.flush()
        lead.party_id = party.id

    contact = None
    if lead.contact_name or lead.email or lead.phone:
        contact = Contact(
            party_id=party.id,
            name=lead.contact_name or lead.company_name,
            title=lead.contact_title,
            email=lead.email,
            phone=lead.phone,
            is_primary=True,
        )
        db.add(contact)
        db.flush()

    opp = None
    if create_opportunity:
        label = (lead.interest or "New opportunity").strip().split("\n", 1)[0][:180]
        opp_name = (opportunity_name or "").strip() or f"{lead.company_name} — {label}"
        expected = amount_expected
        if expected is None:
            expected = lead.estimated_budget if lead.estimated_budget is not None else Decimal("0")
        opp = Opportunity(
            opportunity_number=numbering.next_opportunity_number(db),
            name=opp_name[:255],
            party_id=party.id,
            contact_id=contact.id if contact else None,
            lead_id=lead.id,
            stage="prospecting",
            source=lead.source,
            requirement=lead.interest,
            notes=lead.notes,
            amount_expected=expected,
            close_date=close_date,
            probability=STAGE_PROBABILITY["prospecting"],
            next_step="Confirm the requirement and start needs analysis",
        )
        _set_salesperson(db, opp, owner_id)
        db.add(opp)
        db.flush()
    if lead.salesperson_id is None:
        _set_salesperson(db, lead, owner_id)
    lead.status = "converted"
    db.add(
        Activity(
            lead_id=lead.id,
            opportunity_id=opp.id if opp else None,
            party_id=party.id,
            contact_id=contact.id if contact else None,
            kind="note",
            subject="Lead converted",
            body=(
                f"Created Account, Contact, and Opportunity {opp.opportunity_number}."
                if opp
                else "Created Account and Contact."
            ),
            owner=lead.owner,
            done=True,
        )
    )
    db.flush()
    return lead, opp, party, contact


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> dict:
    leads = db.query(Lead).all()
    opps = db.query(Opportunity).all()
    open_leads = [r for r in leads if r.status in OPEN_LEAD]
    open_opps = [r for r in opps if r.stage in OPEN_OPP]
    won = [r for r in opps if r.stage == "closed_won"]
    lost = [r for r in opps if r.stage == "closed_lost"]
    weighted = sum(float(r.amount_expected or 0) * int(r.probability or 0) / 100.0 for r in open_opps)
    by_stage = {}
    for stage in STAGE_ORDER:
        rows = [r for r in opps if r.stage == stage]
        by_stage[stage] = {
            "count": len(rows),
            "amount": float(sum((r.amount_expected or 0) for r in rows)),
        }
    decided = len(won) + len(lost)
    return {
        "open_leads": len(open_leads),
        "open_opportunities": len(open_opps),
        "pipeline_value": float(sum((r.amount_expected or 0) for r in open_opps)),
        "weighted_forecast": round(weighted, 2),
        "won_count": len(won),
        "won_value": float(sum((r.amount_expected or 0) for r in won)),
        "lost_count": len(lost),
        "win_rate": round((len(won) / decided) * 100, 1) if decided else 0.0,
        "by_stage": by_stage,
    }


@router.get("/team")
def list_team(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> list[dict]:
    rows = db.query(Salesperson).order_by(Salesperson.name).all()
    return [_person_out(r) for r in rows]


@router.post("/team", status_code=201)
def add_person(
    body: PersonIn, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> dict:
    if body.role not in ROLES:
        raise HTTPException(400, "Role must be bdc, bde, or manager")
    row = Salesperson(
        name=body.name.strip(),
        role=body.role,
        email=_blank(body.email),
        phone=_blank(body.phone),
        active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _person_out(row)


@router.patch("/team/{person_id}")
def patch_person(
    person_id: UUID,
    body: PersonPatch,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict:
    row = db.get(Salesperson, person_id)
    if not row:
        raise HTTPException(404, "Sales person not found")
    data = body.model_dump(exclude_unset=True)
    if "role" in data and data["role"] not in ROLES:
        raise HTTPException(400, "Role must be bdc, bde, or manager")
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _person_out(row)


@router.get("/leads")
def list_leads(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> list[dict]:
    rows = db.query(Lead).order_by(Lead.created_at.desc()).all()
    opp_by_lead = {
        o.lead_id: o
        for o in db.query(Opportunity).filter(Opportunity.lead_id.isnot(None)).all()
    }
    return [_lead_out(r, opp_by_lead.get(r.id)) for r in rows]


@router.get("/leads/{lead_id}")
def get_lead(
    lead_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> dict:
    row = db.get(Lead, lead_id)
    if not row:
        raise HTTPException(404, "Lead not found")
    opp = db.query(Opportunity).filter(Opportunity.lead_id == row.id).one_or_none()
    activities = (
        db.query(Activity).filter(Activity.lead_id == row.id).order_by(Activity.created_at.desc()).all()
    )
    data = _lead_out(row, opp)
    data["activities"] = [_activity_out(a) for a in activities]
    return data


@router.post("/leads", status_code=201)
def create_lead(
    body: LeadIn, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> dict:
    status = _normalize_lead_status(body.status) if body.status else "new"
    if status == "converted":
        raise HTTPException(400, "Create the lead first, then use Convert")
    row = Lead(
        lead_number=numbering.next_lead_number(db),
        company_name=body.company_name.strip(),
        contact_name=_compose_contact_name(body),
        contact_title=_blank(body.contact_title),
        email=_blank(body.email),
        phone=_blank(body.phone),
        source=_blank(body.source),
        interest=_blank(body.interest),
        estimated_budget=body.estimated_budget,
        notes=body.notes,
        status=status,
    )
    _set_salesperson(db, row, body.salesperson_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _lead_out(row)


@router.patch("/leads/{lead_id}")
def patch_lead(
    lead_id: UUID,
    body: LeadPatch,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict:
    row = db.get(Lead, lead_id)
    if not row:
        raise HTTPException(404, "Lead not found")
    if row.status == "converted":
        raise HTTPException(400, "Converted leads are read-only. Open the Opportunity instead.")
    data = body.model_dump(exclude_unset=True)
    salesperson_id = data.pop("salesperson_id", None)
    if "salesperson_id" in body.model_fields_set:
        _set_salesperson(db, row, salesperson_id)
    composed = _compose_contact_name(body)
    if composed is not None and ("first_name" in body.model_fields_set or "last_name" in body.model_fields_set or "contact_name" in body.model_fields_set):
        data["contact_name"] = composed
    data.pop("first_name", None)
    data.pop("last_name", None)
    auto_convert = False
    if "status" in data and data["status"] is not None:
        data["status"] = _normalize_lead_status(data["status"])
        if data["status"] == "converted":
            auto_convert = True
            data.pop("status")
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(row, key, value)
    if auto_convert:
        lead, opp, party, _contact = _convert_lead(db, row)
        db.commit()
        return {
            "lead": _lead_out(lead, opp),
            "opportunity": _opp_out(opp, party.legal_name),
            "converted": True,
        }
    if row.status == "qualified" and row.salesperson_id is None:
        raise HTTPException(400, "Assign a BDE or BDC before marking a lead Qualified")
    db.commit()
    db.refresh(row)
    opp = db.query(Opportunity).filter(Opportunity.lead_id == row.id).one_or_none()
    return _lead_out(row, opp)


@router.post("/leads/{lead_id}/convert", status_code=201)
def convert_lead(
    lead_id: UUID,
    body: ConvertIn | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    body = body or ConvertIn()
    lead, opp, party, contact = _convert_lead(
        db,
        lead,
        salesperson_id=body.salesperson_id,
        opportunity_name=body.opportunity_name,
        amount_expected=body.amount_expected,
        close_date=body.close_date,
        create_opportunity=body.create_opportunity,
    )
    db.commit()
    if opp:
        db.refresh(opp)
    return {
        "lead": _lead_out(lead, opp),
        "opportunity": _opp_out(opp, party.legal_name) if opp else None,
        "account_id": str(party.id),
        "account_name": party.legal_name,
        "contact_id": str(contact.id) if contact else None,
        "contact_name": contact.name if contact else None,
    }


@router.get("/opportunities")
def list_opportunities(
    db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> list[dict]:
    rows = (
        db.query(Opportunity)
        .options(joinedload(Opportunity.party))
        .order_by(Opportunity.updated_at.desc())
        .all()
    )
    return [_opp_out(r) for r in rows]


@router.post("/opportunities", status_code=201)
def create_opportunity(
    body: OpportunityIn, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> dict:
    party = db.get(Party, body.party_id)
    if not party:
        raise HTTPException(404, "Account not found")
    if body.salesperson_id is None:
        raise HTTPException(400, "Assign a BDE or BDC to this opportunity")
    row = Opportunity(
        opportunity_number=numbering.next_opportunity_number(db),
        name=body.name.strip(),
        party_id=party.id,
        contact_id=body.contact_id,
        stage="prospecting",
        source=_blank(body.source),
        requirement=_blank(body.requirement) or body.name.strip(),
        amount_expected=body.amount_expected,
        close_date=body.close_date,
        next_step=_blank(body.next_step) or "Confirm the requirement and start needs analysis",
        notes=body.notes,
        probability=STAGE_PROBABILITY["prospecting"],
    )
    _set_salesperson(db, row, body.salesperson_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _opp_out(row, party.legal_name)


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(
    opportunity_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> dict:
    row = (
        db.query(Opportunity)
        .options(joinedload(Opportunity.party))
        .filter(Opportunity.id == opportunity_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "Opportunity not found")
    quotes = (
        db.query(Quote)
        .filter(Quote.opportunity_id == row.id)
        .order_by(Quote.created_at.desc())
        .all()
    )
    invoices = (
        db.query(Invoice)
        .filter(Invoice.opportunity_id == row.id)
        .order_by(Invoice.created_at.desc())
        .all()
    )
    activities = (
        db.query(Activity)
        .filter(Activity.opportunity_id == row.id)
        .order_by(Activity.created_at.desc())
        .all()
    )
    prices = (
        db.query(SupplierPrice)
        .filter(SupplierPrice.opportunity_id == row.id)
        .order_by(SupplierPrice.created_at.desc())
        .all()
    )
    data = _opp_out(row)
    data["quotes"] = [
        {
            "id": str(q.id),
            "quote_number": q.quote_number,
            "status": q.status,
            "total_amount": float(q.total_amount or 0),
        }
        for q in quotes
    ]
    data["invoices"] = [
        {
            "id": str(i.id),
            "invoice_number": i.invoice_number,
            "status": i.status,
            "invoice_type": i.invoice_type,
            "total_amount": float(i.total_amount or 0),
            "amount_paid": float(i.amount_paid or 0),
        }
        for i in invoices
    ]
    data["activities"] = [_activity_out(a) for a in activities]
    data["supplier_prices"] = [_price_out(p) for p in prices]
    return data


@router.patch("/opportunities/{opportunity_id}")
def patch_opportunity(
    opportunity_id: UUID,
    body: OpportunityPatch,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict:
    row = db.get(Opportunity, opportunity_id)
    if not row:
        raise HTTPException(404, "Opportunity not found")
    data = body.model_dump(exclude_unset=True)
    salesperson_id = data.pop("salesperson_id", None)
    if "salesperson_id" in body.model_fields_set:
        _set_salesperson(db, row, salesperson_id)
    if "stage" in data and data["stage"] is not None:
        data["stage"] = _normalize_stage(data["stage"])
        if "probability" not in data:
            data["probability"] = STAGE_PROBABILITY[data["stage"]]
    if "fulfillment_status" in data and data["fulfillment_status"] not in FULFILLMENT:
        raise HTTPException(400, "Unknown fulfillment status")
    if "probability" in data and data["probability"] is not None:
        data["probability"] = max(0, min(100, int(data["probability"])))
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    party = db.get(Party, row.party_id)
    return _opp_out(row, party.legal_name if party else None)


@router.post("/opportunities/{opportunity_id}/supplier-prices", status_code=201)
def add_supplier_price(
    opportunity_id: UUID,
    body: SupplierPriceIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict:
    row = db.get(Opportunity, opportunity_id)
    if not row:
        raise HTTPException(404, "Opportunity not found")
    if body.supplier_kind not in ("oem", "distributor"):
        raise HTTPException(400, "Say whether this price is from an OEM or a distributor")
    if row.stage in ("closed_won", "closed_lost"):
        raise HTTPException(400, "This opportunity is already closed")
    status = "requested"
    if body.unit_cost and body.unit_cost > 0:
        status = "received"
    if body.sell_unit_price and body.sell_unit_price > 0:
        status = "chosen"
    price = SupplierPrice(
        opportunity_id=row.id,
        supplier_name=body.supplier_name.strip(),
        supplier_kind=body.supplier_kind,
        item_name=body.item_name.strip(),
        sku=_blank(body.sku),
        quantity=body.quantity,
        unit_cost=body.unit_cost,
        sell_unit_price=body.sell_unit_price,
        gst_rate=body.gst_rate,
        quote_ref=_blank(body.quote_ref),
        valid_until=body.valid_until,
        status=status,
        notes=body.notes,
    )
    db.add(price)
    if row.stage == "prospecting":
        row.stage = "needs_analysis"
        row.probability = STAGE_PROBABILITY["needs_analysis"]
    db.commit()
    db.refresh(price)
    return _price_out(price)


@router.patch("/supplier-prices/{price_id}")
def patch_supplier_price(
    price_id: UUID,
    body: SupplierPricePatch,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict:
    row = db.get(SupplierPrice, price_id)
    if not row:
        raise HTTPException(404, "Supplier price not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in PRICE_STATUS:
        raise HTTPException(400, "Unknown price status")
    if data.get("status") == "chosen":
        sell = data.get("sell_unit_price", row.sell_unit_price)
        if sell is None or Decimal(str(sell)) <= 0:
            raise HTTPException(400, "Enter our selling price before choosing this supplier price")
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _price_out(row)


@router.post("/opportunities/{opportunity_id}/customer-quote", status_code=201)
def customer_quote_from_prices(
    opportunity_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> dict:
    row = db.get(Opportunity, opportunity_id)
    if not row:
        raise HTTPException(404, "Opportunity not found")
    if row.stage in ("closed_won", "closed_lost"):
        raise HTTPException(400, "Closed opportunities cannot get a new quote from this action")
    prices = (
        db.query(SupplierPrice)
        .filter(SupplierPrice.opportunity_id == row.id, SupplierPrice.status == "chosen")
        .all()
    )
    usable = [p for p in prices if p.sell_unit_price and p.sell_unit_price > 0]
    if not usable:
        raise HTTPException(
            400,
            "Choose at least one OEM or distributor price and enter what the customer will pay",
        )
    party = db.get(Party, row.party_id)
    if not party:
        raise HTTPException(404, "Account not found")
    lines = []
    for price in usable:
        desc = price.item_name
        if price.quote_ref:
            desc = f"{price.item_name} ({price.supplier_name} {price.quote_ref})"
        lines.append(
            {
                "sku": (price.sku or "RESALE")[:64],
                "description": desc[:500],
                "vendor_name": price.supplier_name,
                "quantity": price.quantity,
                "unit_price": price.sell_unit_price,
                "gst_rate": price.gst_rate,
                "billing_model": "one_time",
            }
        )
    try:
        quote = quote_engine.build_quote(
            db,
            party=party,
            line_specs=lines,
            opportunity_id=row.id,
            opportunity_name=row.name,
            sales_owner=row.owner,
            notes="Customer quote built from OEM / distributor prices on this opportunity.",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    fresh = db.get(Opportunity, row.id)
    if fresh:
        fresh.amount_expected = quote.total_amount
        if fresh.stage in ("prospecting", "needs_analysis"):
            fresh.stage = "proposal"
            fresh.probability = STAGE_PROBABILITY["proposal"]
        db.commit()
    return {
        "quote_id": str(quote.id),
        "quote_number": quote.quote_number,
        "total_amount": float(quote.total_amount or 0),
    }


@router.post("/opportunities/{opportunity_id}/activities", status_code=201)
def add_opportunity_activity(
    opportunity_id: UUID,
    body: ActivityIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict:
    row = db.get(Opportunity, opportunity_id)
    if not row:
        raise HTTPException(404, "Opportunity not found")
    if body.kind not in ACTIVITY_KINDS:
        raise HTTPException(400, "Unknown activity type")
    if row.stage == "prospecting" and body.kind in ("call", "email", "meeting"):
        row.stage = "needs_analysis"
        row.probability = STAGE_PROBABILITY["needs_analysis"]
    act = Activity(
        opportunity_id=row.id,
        party_id=row.party_id,
        contact_id=row.contact_id,
        kind=body.kind,
        subject=body.subject.strip(),
        body=body.body,
        due_on=body.due_on,
        owner=_blank(body.owner) or row.owner,
        done=body.kind == "note",
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return _activity_out(act)


@router.post("/leads/{lead_id}/activities", status_code=201)
def add_lead_activity(
    lead_id: UUID,
    body: ActivityIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> dict:
    row = db.get(Lead, lead_id)
    if not row:
        raise HTTPException(404, "Lead not found")
    if body.kind not in ACTIVITY_KINDS:
        raise HTTPException(400, "Unknown activity type")
    if row.status == "new" and body.kind in ("call", "email", "meeting"):
        row.status = "contacted"
    act = Activity(
        lead_id=row.id,
        party_id=row.party_id,
        kind=body.kind,
        subject=body.subject.strip(),
        body=body.body,
        due_on=body.due_on,
        owner=_blank(body.owner) or row.owner,
        done=body.kind == "note",
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return _activity_out(act)
