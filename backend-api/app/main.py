"""
KB-012: app/main.py is app wiring only - environment/app metadata, the
FastAPI app object, and router registration. All route logic (system,
admin, customer, auth) now lives under app/api/routes/.
"""

import os

from fastapi import FastAPI

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.customer import router as customer_router
from app.api.routes.health import router as health_router

APP_NAME = os.getenv("APP_NAME", "MSSP Control Plane API")
APP_ENV = os.getenv("APP_ENV", "development")

app = FastAPI(
    title=APP_NAME,
    description="Backend API foundation for the MSSP Control Plane.",
    version="0.1.0",
)

# KB-010: auth/RBAC foundation. Public: POST /auth/login, GET /auth/roles.
# Protected: GET /auth/me.
app.include_router(auth_router)

# KB-012: system endpoints (public). Was inline in main.py through KB-011.
app.include_router(health_router)

# KB-011 protection (require_roles/get_current_user/require_tenant_match) is
# implemented inside these routers - see app/api/routes/admin.py and
# app/api/routes/customer.py. KB-012 only moved the route code out of
# main.py; it did not change any auth/RBAC/tenant-isolation behavior.
app.include_router(admin_router)
app.include_router(customer_router)
