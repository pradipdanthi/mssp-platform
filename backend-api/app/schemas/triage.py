"""KB-056 request schemas for Admin/SOC alert and incident triage."""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


AlertStatus = Literal["new", "triaged", "incident_created", "false_positive", "closed"]
AiTriageStatus = Literal["draft", "accepted", "rejected", "stale"]
IncidentStatus = Literal["open", "in_progress", "waiting_customer", "resolved", "closed"]
CommentVisibility = Literal["internal", "customer"]


class AlertTriageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[AlertStatus] = None
    customer_visible: Optional[bool] = None
    # Customer-facing copy SOC can polish before enabling visibility.
    ai_plain_summary: Optional[str] = Field(default=None, max_length=4000)
    ai_recommended_action: Optional[str] = Field(default=None, max_length=4000)
    # KB-096: human finalize of AI SOC triage draft (accept / reject).
    ai_triage_status: Optional[AiTriageStatus] = None

    @model_validator(mode="after")
    def require_update(self) -> "AlertTriageUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one triage field must be provided")
        # Status / visibility flags cannot be null when sent.
        for field in ("status", "customer_visible", "ai_triage_status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        # Text fields: blank string → store as NULL (clear).
        for field in ("ai_plain_summary", "ai_recommended_action"):
            if field in self.model_fields_set:
                value = getattr(self, field)
                if value is not None:
                    cleaned = value.strip()
                    setattr(self, field, cleaned or None)
        return self


class IncidentTriageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[IncidentStatus] = None
    assigned_to_user_id: Optional[UUID] = None
    customer_visible_summary: Optional[str] = Field(default=None, max_length=10000)
    customer_action_required: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def require_update(self) -> "IncidentTriageUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one triage field must be provided")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        for field in ("customer_visible_summary", "customer_action_required"):
            if field in self.model_fields_set:
                value = getattr(self, field)
                if value is not None:
                    cleaned = value.strip()
                    setattr(self, field, cleaned or None)
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
