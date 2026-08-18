"""
KB-012: System endpoints, moved out of app/main.py during route
modularization. Behavior is unchanged from the original main.py versions -
only the file/router they live in changed.

- GET /       - public, basic service info
- GET /health - public, reports API/database/Redis status
"""

import logging
import os
from typing import Any, Dict

from fastapi import APIRouter

from app.db.session import fetch_one, redis_client

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)

APP_ENV = os.getenv("APP_ENV", "development")


@router.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "mssp-backend-api",
        "status": "running",
        "environment": APP_ENV,
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health")
def health() -> Dict[str, Any]:
    db_status = "unknown"
    redis_status = "unknown"

    try:
        row = fetch_one("SELECT 1 AS ok;")
        db_status = "ok" if row.get("ok") == 1 else "error"
    except Exception as exc:
        logger.exception("health database check failed")
        db_status = "error"

    try:
        pong = redis_client().ping()
        redis_status = "ok" if pong else "error"
    except Exception as exc:
        logger.exception("health redis check failed")
        redis_status = "error"

    api_status = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return {
        "api": api_status,
        "service": "mssp-backend-api",
        "environment": APP_ENV,
        "database": db_status,
        "redis": redis_status,
    }
