"""KB-066: Admin reports, protected assets, and audit log schemas."""

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ReportStatusLiteral = Literal["draft", "published", "archived"]
AssetTypeLiteral = Literal[
    "server", "workstation", "firewall", "network_device", "application", "database", "other"
]
AssetCriticalityLiteral = Literal["low", "medium", "high", "critical"]
AssetStatusLiteral = Literal["active", "inactive", "unknown"]


class ReportCreateRequest(BaseModel):
    tenant_id: UUID
    report_month: date
    executive_summary: Optional[str] = Field(default=None, max_length=20000)
    status: ReportStatusLiteral = "draft"
    period_highlights: Optional[str] = Field(default=None, max_length=10000)
    trends: Optional[str] = Field(default=None, max_length=10000)
    next_month_focus: Optional[str] = Field(default=None, max_length=10000)
    leadership_asks: Optional[str] = Field(default=None, max_length=10000)


class ReportUpdateRequest(BaseModel):
    executive_summary: Optional[str] = Field(default=None, max_length=20000)
    status: Optional[ReportStatusLiteral] = None
    period_highlights: Optional[str] = Field(default=None, max_length=10000)
    trends: Optional[str] = Field(default=None, max_length=10000)
    next_month_focus: Optional[str] = Field(default=None, max_length=10000)
    leadership_asks: Optional[str] = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ReportUpdateRequest":
        if all(v is None for v in self.__dict__.values()):
            raise ValueError("At least one field must be provided")
        return self


class ReportDetail(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    short_code: str
    report_month: str
    title: str
    status: str
    executive_summary: Optional[str] = None
    published_at: Optional[str] = None
    created_at: str
    updated_at: str
    # KB-067: customer-safe projected sections (never raw metrics / file path).
    sections: Optional[dict] = None


class AssetCreateRequest(BaseModel):
    tenant_id: UUID
    hostname: Optional[str] = Field(default=None, max_length=255)
    asset_type: AssetTypeLiteral = "server"
    criticality: AssetCriticalityLiteral = "medium"
    status: AssetStatusLiteral = "active"
    os_name: Optional[str] = Field(default=None, max_length=120)
    owner: Optional[str] = Field(default=None, max_length=200)
    appliance_id: Optional[UUID] = None


class AssetUpdateRequest(BaseModel):
    hostname: Optional[str] = Field(default=None, max_length=255)
    asset_type: Optional[AssetTypeLiteral] = None
    criticality: Optional[AssetCriticalityLiteral] = None
    status: Optional[AssetStatusLiteral] = None
    os_name: Optional[str] = Field(default=None, max_length=120)
    owner: Optional[str] = Field(default=None, max_length=200)
    appliance_id: Optional[UUID] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "AssetUpdateRequest":
        if all(v is None for v in self.__dict__.values()):
            raise ValueError("At least one field must be provided")
        return self


class AssetDetail(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    short_code: str
    appliance_id: Optional[str] = None
    appliance_name: Optional[str] = None
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    asset_type: str
    os_name: Optional[str] = None
    criticality: str
    owner: Optional[str] = None
    status: str
    last_seen_at: Optional[str] = None
    created_at: str
    updated_at: str


class AuditLogRow(BaseModel):
    id: str
    tenant_name: Optional[str] = None
    short_code: Optional[str] = None
    actor_email: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    source_ip: Optional[str] = None
    created_at: str
