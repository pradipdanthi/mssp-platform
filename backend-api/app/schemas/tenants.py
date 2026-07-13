"""
KB-013: Request/response models for the /admin/tenants/* management
endpoints (GET one, POST, PATCH).

These are separate from the existing, untouched GET /admin/tenants list
endpoint in app/api/routes/admin.py, which keeps returning its own untyped
dict shape exactly as before KB-013.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

StatusLiteral = Literal["onboarding", "active", "inactive", "suspended"]
SlaLevelLiteral = Literal["standard", "business", "premium", "24x7"]
CriticalityLiteral = Literal["low", "medium", "high", "critical"]


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    short_code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    status: StatusLiteral = "active"
    sla_level: SlaLevelLiteral = "standard"
    business_criticality: CriticalityLiteral = "medium"
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def normalize_short_code(self) -> "TenantCreateRequest":
        self.short_code = self.short_code.strip().upper()
        return self


class TenantUpdateRequest(BaseModel):
    """
    All fields optional (PATCH semantics) - at least one must be provided.
    short_code is intentionally not updatable in KB-013: it is used as a
    stable identifier elsewhere (e.g. /customer/* URLs), so changing it is
    left out of scope for this module.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[StatusLiteral] = None
    sla_level: Optional[SlaLevelLiteral] = None
    business_criticality: Optional[CriticalityLiteral] = None
    timezone: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "TenantUpdateRequest":
        if all(v is None for v in self.__dict__.values()):
            raise ValueError("At least one field must be provided")
        return self


class TenantDetail(BaseModel):
    id: str
    name: str
    short_code: str
    status: str
    sla_level: str
    business_criticality: str
    timezone: str
    notes: Optional[str] = None
    created_at: str
    updated_at: str
    appliances: int
    protected_assets: int
    incidents: int
