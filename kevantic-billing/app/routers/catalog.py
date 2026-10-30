from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import CatalogItem
from app.schemas import CatalogItemIn, CatalogItemOut, CatalogItemUpdate

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


@router.post("", response_model=CatalogItemOut, status_code=201)
def create_catalog_item(
    body: CatalogItemIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> CatalogItem:
    sku = body.sku.strip()
    exists = db.query(CatalogItem).filter(CatalogItem.sku == sku).one_or_none()
    if exists:
        raise HTTPException(400, "That part number is already in the catalog")
    if body.billing_model not in ("subscription", "one_time", "usage"):
        raise HTTPException(400, "Billing model must be subscription, one_time, or usage")
    item = CatalogItem(
        sku=sku,
        name=body.name.strip(),
        description=body.description,
        vendor_name=(body.vendor_name or "").strip() or None,
        product_family=(body.product_family or "resale").strip() or "resale",
        billing_model=body.billing_model,
        unit_label=(body.unit_label or "unit").strip() or "unit",
        list_price=body.list_price,
        gst_rate=body.gst_rate,
        hsn_sac=(body.hsn_sac or "").strip() or None,
        min_qty=max(body.min_qty, 1),
        active=True,
        sort_order=200,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


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
