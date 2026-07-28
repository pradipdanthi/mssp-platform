"""KB-069: vulnerability ingest + recommendation promotion schemas."""

from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

SeverityLiteral = Literal["low", "medium", "high", "critical"]
VulnStatusLiteral = Literal["open", "fixed", "accepted_risk", "false_positive", "closed"]
SourcePlatformLiteral = Literal[
    "greenbone",
    "openvas",
    "nuclei",
    "vuls",
    "manual",
    "other",
]


class VulnFindingIngest(BaseModel):
    external_finding_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    severity: SeverityLiteral
    cve_id: Optional[str] = Field(default=None, max_length=64)
    nvt_oid: Optional[str] = Field(default=None, max_length=128)
    protected_asset_id: Optional[UUID] = None
    asset_hostname: Optional[str] = Field(default=None, max_length=255)
    customer_safe_summary: Optional[str] = Field(default=None, max_length=5000)
    remediation_summary: Optional[str] = Field(default=None, max_length=10000)
    internal_notes: Optional[str] = Field(default=None, max_length=10000)
    # null = auto for high/critical per KB-053; true/false overrides.
    create_recommendation: Optional[bool] = None
    # Safer default: draft recommendations stay SOC-hidden until promote/edit.
    recommendation_customer_visible: bool = False


class VulnSyncRequest(BaseModel):
    tenant_short_code: str = Field(min_length=1, max_length=32)
    source_platform: SourcePlatformLiteral = "greenbone"
    findings: List[VulnFindingIngest] = Field(min_length=1, max_length=200)


class VulnFindingResult(BaseModel):
    external_finding_id: str
    vulnerability_id: str
    action: Literal["created", "updated"]
    recommendation_id: Optional[str] = None
    recommendation_action: Optional[Literal["created", "existing", "skipped"]] = None


class VulnSyncResponse(BaseModel):
    tenant_id: str
    short_code: str
    results: List[VulnFindingResult]


class VulnerabilityListItem(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    short_code: str
    protected_asset_id: Optional[str] = None
    asset_hostname: Optional[str] = None
    source_platform: str
    external_finding_id: Optional[str] = None
    cve_id: Optional[str] = None
    title: str
    severity: str
    status: str
    recommendation_id: Optional[str] = None
    first_seen_at: str
    last_seen_at: str
    created_at: str


class VulnerabilityDetail(VulnerabilityListItem):
    nvt_oid: Optional[str] = None
    customer_safe_summary: Optional[str] = None
    remediation_summary: Optional[str] = None
    internal_notes: Optional[str] = None
    updated_at: str


class VulnerabilityPromoteRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    customer_visible: bool = False
    priority: Optional[SeverityLiteral] = None


class VulnerabilityPromoteResponse(BaseModel):
    vulnerability_id: str
    recommendation_id: str
    created: bool
    customer_visible: bool
