"""
Appliance Management plane entrypoint (VM 114).

Hosts only appliance-facing surfaces that must leave mssp-control (KB-093 §12):
register, heartbeat, channel, alert ingest, telemetry.
Admin/Customer portals stay on VM 100.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from typing import Any, Dict

from app.api.routes.appliance_agent import router as appliance_agent_router
from app.api.routes.appliance_alert_ingest import router as appliance_alert_ingest_router
from app.api.routes.appliance_channel import router as appliance_channel_router
from app.api.routes.telemetry_ingest import router as telemetry_ingest_router
from app.core.error_handlers import validation_exception_handler
from app.db.session import fetch_one, redis_client

app = FastAPI(
    title=os.getenv("APP_NAME", "Kevantic Appliance Management API"),
    version=os.getenv("APP_VERSION", "0.1.0"),
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(appliance_agent_router)
app.include_router(appliance_channel_router)
app.include_router(appliance_alert_ingest_router)
app.include_router(telemetry_ingest_router)

APP_ENV = os.getenv("APP_ENV", "production")
logger = logging.getLogger(__name__)


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "kevantic-appliance-mgmt",
        "plane": "appliance_management",
        "status": "running",
        "environment": APP_ENV,
        "health": "/health",
        "note": "Channel/register/heartbeat/alerts only — Admin UI remains on control plane",
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    db_status = "unknown"
    redis_status = "unknown"
    try:
        row = fetch_one("SELECT 1 AS ok;")
        db_status = "ok" if row.get("ok") == 1 else "error"
    except Exception:
        logger.exception("appliance mgmt health database check failed")
        db_status = "error"
    try:
        pong = redis_client().ping()
        redis_status = "ok" if pong else "error"
    except Exception:
        logger.exception("appliance mgmt health redis check failed")
        redis_status = "error"
    api_status = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return {
        "api": api_status,
        "service": "kevantic-appliance-mgmt",
        "plane": "appliance_management",
        "environment": APP_ENV,
        "database": db_status,
        "redis": redis_status,
    }
