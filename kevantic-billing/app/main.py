from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import require_admin
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.routers import catalog, invoices, parties, quotes
from app.services.catalog_seed import seed_catalog

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Kevantic Quote & Billing",
    description=(
        "Standalone enterprise quoting (CPQ) and Tally-style GST invoicing "
        "for the NikTiar product portfolio. Portable Docker stack — not part of "
        "mssp-control Admin/Customer portals."
    ),
    version="1.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_catalog(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "kevantic-billing",
        "database": "ok" if db_ok else "error",
        "company": settings.company_name,
        "port": 8090,
    }


@app.get("/api/me")
def me(user: str = Depends(require_admin)) -> dict:
    settings = get_settings()
    return {
        "user": user,
        "company_name": settings.company_name,
        "company_gstin": settings.company_gstin,
        "company_state": settings.company_state,
        "company_state_code": settings.company_state_code,
        "currency": settings.default_currency,
        "lut_filed": settings.lut_filed,
    }


app.include_router(parties.router)
app.include_router(catalog.router)
app.include_router(quotes.router)
app.include_router(invoices.router)

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/")
def ui_index() -> FileResponse:
    index = STATIC_DIR / "index.html"
    return FileResponse(index)
