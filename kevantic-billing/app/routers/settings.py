from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.schemas import CompanyProfileIn, CompanyProfileOut
from app.services.company import get_or_create_profile
from app.services.india_states import INDIA_STATES

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/company", response_model=CompanyProfileOut)
def get_company(
    db: Session = Depends(get_db), _: str = Depends(require_admin)
) -> CompanyProfileOut:
    return get_or_create_profile(db)


@router.put("/company", response_model=CompanyProfileOut)
def update_company(
    body: CompanyProfileIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> CompanyProfileOut:
    row = get_or_create_profile(db)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.get("/states")
def list_states(_: str = Depends(require_admin)) -> list[dict]:
    return INDIA_STATES
