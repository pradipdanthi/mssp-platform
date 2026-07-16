"""KB-056 request schemas for Admin/SOC alert and incident triage."""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


AlertStatus = Literal["new", "triaged", "incident_created", "false_positive", "closed"]
IncidentStatus = Literal["open", "in_progress", "waiting_customer", "resolved", "closed"]
CommentVisibility = Literal["internal", "customer"]


class AlertTriageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[AlertStatus] = None
    customer_visible: Optional[bool] = None

    @model_validator(mode="after")
    def require_update(self) -> "AlertTriageUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one triage field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Triage fields cannot be null")
        return self


class IncidentTriageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[IncidentStatus] = None
    assigned_to_user_id: Optional[UUID] = None
    customer_visible_summary: Optional[str] = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def require_update(self) -> "IncidentTriageUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one triage field must be provided")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class IncidentCommentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment_text: str = Field(min_length=1, max_length=10000)
    visibility: CommentVisibility = "internal"

    @model_validator(mode="after")
    def normalize_comment(self) -> "IncidentCommentCreateRequest":
        self.comment_text = self.comment_text.strip()
        if not self.comment_text:
            raise ValueError("comment_text cannot be blank")
        return self
