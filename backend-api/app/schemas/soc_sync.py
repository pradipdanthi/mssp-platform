"""KB-061: normalized SOC sync request/response (TheHive/Shuffle → control plane)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SeverityLiteral = Literal["low", "medium", "high", "critical"]


class SocSyncRequest(BaseModel):
    """Safe normalized fields only; no raw TheHive/Wazuh JSON."""

    model_config = ConfigDict(extra="forbid")

    source_tool: str = Field(min_length=1, max_length=100)
    external_alert_id: str = Field(min_length=1, max_length=255)
    severity: SeverityLiteral
    alert_title: str = Field(min_length=1, max_length=500)
    alert_description: Optional[str] = Field(default=None, max_length=4000)
    event_time: Optional[datetime] = None
    destination_host: Optional[str] = Field(default=None, max_length=255)
    destination_ip: Optional[str] = Field(default=None, max_length=64)
    source_ip: Optional[str] = Field(default=None, max_length=64)
    source_user: Optional[str] = Field(default=None, max_length=255)
    wazuh_agent_id: Optional[str] = Field(default=None, max_length=64)
    technical_summary: Optional[str] = Field(default=None, max_length=4000)
    tenant_short_code: str = Field(min_length=2, max_length=32)
    # If None: create incident automatically for high/critical.
    create_incident: Optional[bool] = None
    customer_visible_summary: Optional[str] = Field(default=None, max_length=4000)
    business_impact: Optional[str] = Field(default=None, max_length=4000)


class SocSyncResponse(BaseModel):
    alert_id: str
    incident_id: Optional[str] = None
    incident_number: Optional[str] = None
    duplicate: bool
    customer_visible: bool
    status: str
    message: str
