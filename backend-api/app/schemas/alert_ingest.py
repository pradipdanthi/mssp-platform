"""KB-057 request/response models for customer-safe appliance alert ingest."""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SeverityLiteral = Literal["low", "medium", "high", "critical"]


class ApplianceAlertIngestRequest(BaseModel):
    """Normalized fields only; unknown and unsafe fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    source_tool: str = Field(min_length=1, max_length=100)
    external_alert_id: str = Field(min_length=1, max_length=255)
    severity: SeverityLiteral
    alert_title: str = Field(min_length=1, max_length=500)
    alert_description: Optional[str] = Field(default=None, max_length=4000)
    event_time: Optional[datetime] = None
    destination_host: Optional[str] = Field(default=None, max_length=255)
    source_ip: Optional[str] = Field(default=None, max_length=64)
    destination_ip: Optional[str] = Field(default=None, max_length=64)
    source_user: Optional[str] = Field(default=None, max_length=255)
    raw_event: Optional[Dict[str, Any]] = None
    mitre_mapping: Optional[Dict[str, Any]] = None
    # Optional appliance-local AI pre-triage (absent on older appliances — OK).
    appliance_ai_verdict: Optional[str] = Field(default=None, max_length=64)
    appliance_ai_confidence: Optional[float] = Field(default=None, ge=0, le=100)
    appliance_ai_summary: Optional[str] = Field(default=None, max_length=2000)

    # Deliberately absent: tenant_id, appliance_id, customer_visible,
    # local_ip, internal/admin notes, credentials, tokens, and
    # packet/full-log payloads. raw_event must already be scrubbed on appliance.


class ApplianceAlertIngestResponse(BaseModel):
    alert_id: str
    duplicate: bool
    customer_visible: bool
    status: str
    message: str
