from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import Party
from app.schemas import PartyIn, PartyOut

router = APIRouter(prefix="/api/parties", tags=["parties"])


@router.get("", response_model=list[PartyOut])
def list_parties(
    db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> list[Party]:
    return db.query(Party).order_by(Party.legal_name).all()


@router.post("", response_model=PartyOut, status_code=201)
def create_party(
    body: PartyIn, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Party:
    party = Party(**body.model_dump())
    db.add(party)
    db.commit()
    db.refresh(party)
    return party


@router.get("/{party_id}", response_model=PartyOut)
def get_party(
    party_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> Party:
    party = db.get(Party, party_id)
    if not party:
        raise HTTPException(404, "Party not found")
    return party


@router.put("/{party_id}", response_model=PartyOut)
def update_party(
    party_id: UUID,
    body: PartyIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Party:
    party = db.get(Party, party_id)
    if not party:
        raise HTTPException(404, "Party not found")
    for k, v in body.model_dump().items():
        setattr(party, k, v)
    db.commit()
    db.refresh(party)
    return party
