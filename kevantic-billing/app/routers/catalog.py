from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import CatalogItem
from app.schemas import CatalogItemOut, CatalogItemUpdate

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("", response_model=list[CatalogItemOut])
def list_catalog(
    active_only: bool = True,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> list[CatalogItem]:
    q = db.query(CatalogItem)
    if active_only:
        q = q.filter(CatalogItem.active.is_(True))
    return q.order_by(CatalogItem.sort_order, CatalogItem.name).all()


@router.patch("/{item_id}", response_model=CatalogItemOut)
def update_catalog_item(
    item_id: UUID,
    body: CatalogItemUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> CatalogItem:
    item = db.get(CatalogItem, item_id)
    if not item:
        raise HTTPException(404, "Catalog item not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item
