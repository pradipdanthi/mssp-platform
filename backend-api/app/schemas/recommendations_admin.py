"""KB-066: Admin recommendation create/update schemas."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

PriorityLiteral = Literal["low", "medium", "high", "critical"]
StatusLiteral = Literal["open", "in_progress", "accepted_risk", "completed", "dismissed"]


class RecommendationCreateRequest(BaseModel):
    tenant_id: UUID
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=20000)
    priority: PriorityLiteral = "medium"
    category: str = Field(default="general", min_length=1, max_length=100)
    status: StatusLiteral = "open"
    # Safer MSSP default: hidden until SOC explicitly shares with customer.
    customer_visible: bool = False
    due_at: Optional[datetime] = None
    related_alert_id: Optional[UUID] = None
    related_incident_id: Optional[UUID] = None


class RecommendationUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    priority: Optional[PriorityLiteral] = None
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    status: Optional[StatusLiteral] = None
    customer_visible: Optional[bool] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    related_alert_id: Optional[UUID] = None
    related_incident_id: Optional[UUID] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "RecommendationUpdateRequest":
        if all(v is None for v in self.__dict__.values()):
            raise ValueError("At least one field must be provided")
        return self


class RecommendationDetail(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    short_code: str
    title: str
    description: str
    priority: str
    category: str
    status: str
    customer_visible: bool
    due_at: Optional[str] = None
    completed_at: Optional[str] = None
    related_alert_id: Optional[str] = None
    related_incident_id: Optional[str] = None
    related_vulnerability_id: Optional[str] = None
    created_at: str
    updated_at: str
