from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import require_admin
from app.db import Base, SessionLocal, engine
from app.routers import catalog, dashboard, invoices, parties, quotes, settings
from app.services.catalog_seed import seed_catalog
from app.services.company import get_or_create_profile
from app.services.migrate import run_migrations

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Kevantic Quote & Billing",
    description=(
        "Standalone enterprise quoting (CPQ) and Tally-style GST invoicing "
        "for the NikTiar product portfolio. Portable Docker stack — not part of "
        "mssp-control Admin/Customer portals."
    ),
    version="1.1.0",
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    db = SessionLocal()
    try:
        seed_catalog(db)
        get_or_create_profile(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
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
        "version": "1.1.0",
        "database": "ok" if db_ok else "error",
        "port": 8090,
    }


@app.get("/api/me")
def me(user: str = Depends(require_admin)) -> dict:
    db = SessionLocal()
    try:
        profile = get_or_create_profile(db)
        return {
            "user": user,
            "company_name": profile.legal_name,
            "company_gstin": profile.gstin or "",
            "company_state": profile.state,
            "company_state_code": profile.state_code,
            "currency": profile.currency,
            "lut_filed": profile.lut_filed,
            "version": "1.1.0",
        }
    finally:
        db.close()


app.include_router(parties.router)
app.include_router(catalog.router)
app.include_router(quotes.router)
app.include_router(invoices.router)
app.include_router(dashboard.router)
app.include_router(settings.router)

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/")
def ui_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
