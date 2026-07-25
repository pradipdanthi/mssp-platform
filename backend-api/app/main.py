"""
KB-012: app/main.py is app wiring only - environment/app metadata, the
FastAPI app object, and router registration. All route logic (system,
admin, customer, auth) now lives under app/api/routes/.
"""

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.routes.admin import router as admin_router
from app.api.routes.admin_ops import router as admin_ops_router
from app.api.routes.alert_incident_triage import router as alert_incident_triage_router
from app.api.routes.appliance_agent import router as appliance_agent_router
from app.api.routes.appliance_alert_ingest import router as appliance_alert_ingest_router
from app.api.routes.appliance_management import router as appliance_management_router
from app.api.routes.auth import router as auth_router
from app.api.routes.customer import router as customer_router
from app.api.routes.health import router as health_router
from app.api.routes.on_prem_template import router as on_prem_template_router
from app.api.routes.recommendation_management import router as recommendation_management_router
from app.api.routes.soc_sync import router as soc_sync_router
from app.api.routes.tenant_management import router as tenant_management_router
from app.api.routes.user_management import router as user_management_router
from app.core.error_handlers import validation_exception_handler

APP_NAME = os.getenv("APP_NAME", "MSSP Control Plane API")
APP_ENV = os.getenv("APP_ENV", "development")

app = FastAPI(
    title=APP_NAME,
    description="Backend API foundation for the MSSP Control Plane.",
    version="0.1.0",
)

# KB-014 fix: sanitize 422 validation-error responses globally so a
# whole-model validator error (e.g. UserCreateRequest's role/tenant_id
# check) can never echo a submitted password/new_password value back to the
# caller. See app/core/error_handlers.py for the full explanation. This
# changes response *content* only for errors that contain a sensitive key -
# the 422 status code and {"detail": [...]} shape are unchanged, and every
# other existing 422 response (e.g. KB-013's tenant validation errors) is
# unaffected.
app.add_exception_handler(RequestValidationError, validation_exception_handler)

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
app.include_router(alert_incident_triage_router)
app.include_router(recommendation_management_router)
app.include_router(admin_ops_router)
app.include_router(customer_router)

# KB-013: admin tenant management (GET one, POST, PATCH) - adds alongside
# admin_router's existing GET /admin/tenants without modifying admin.py.
app.include_router(tenant_management_router)

# KB-014: admin user management (list, GET one, POST, PATCH, PATCH password).
app.include_router(user_management_router)

# KB-058: this static path must be registered before KB-015's dynamic
# /admin/appliances/{appliance_id} path so "on-prem-template" is not parsed
# as an appliance UUID.
app.include_router(on_prem_template_router)

# KB-015: admin appliance management (GET/PATCH one appliance, create/list/
# revoke appliance activation tokens for a tenant).
app.include_router(appliance_management_router)

# KB-016: appliance-facing registration and heartbeat receiver (no human
# JWT/RBAC - authenticated by activation token / durable appliance API key
# instead, see app/api/routes/appliance_agent.py).
app.include_router(appliance_agent_router)

# KB-057: authenticated appliance alert ingestion with normalized safe fields.
app.include_router(appliance_alert_ingest_router)

# KB-061: Shuffle/TheHive → control plane normalized sync (X-SOC-Sync-Key).
app.include_router(soc_sync_router)
