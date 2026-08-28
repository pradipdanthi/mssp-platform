"""Schemas for alert suppressions and admin bulk triage."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


SuppressionScope = Literal["global", "tenant", "host"]
BulkAlertStatus = Literal["false_positive", "closed"]
BulkAlertAction = Literal["approve_ai_low_priority"]
BulkIncidentStatus = Literal["closed", "resolved"]
BulkIncidentCloseReason = Literal["false_positive", "benign_admin_activity", "resolved"]


class SuppressionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: SuppressionScope
    rule_id: str = Field(min_length=1, max_length=128)
    tenant_id: Optional[UUID] = None
    hostname: Optional[str] = Field(default=None, max_length=255)
    match_process_path: bool = False
    process_path_value: Optional[str] = Field(default=None, max_length=1000)
    match_parent_process: bool = False
    parent_process_value: Optional[str] = Field(default=None, max_length=1000)
    match_file_hash: bool = False
    file_hash_value: Optional[str] = Field(default=None, max_length=128)
    match_hostname: bool = False
    hostname_value: Optional[str] = Field(default=None, max_length=255)
    expires_at: Optional[datetime] = None
    reason: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_scope_and_matches(self) -> "SuppressionCreateRequest":
        self.rule_id = self.rule_id.strip()
        if not self.rule_id:
            raise ValueError("rule_id cannot be blank")

        if self.hostname is not None:
            self.hostname = self.hostname.strip() or None
        if self.hostname_value is not None:
            self.hostname_value = self.hostname_value.strip() or None
        if self.process_path_value is not None:
            self.process_path_value = self.process_path_value.strip() or None
        if self.parent_process_value is not None:
            self.parent_process_value = self.parent_process_value.strip() or None
        if self.file_hash_value is not None:
            self.file_hash_value = self.file_hash_value.strip().lower() or None
        if self.reason is not None:
            self.reason = self.reason.strip() or None

        if self.scope == "global":
            if self.tenant_id is not None or self.hostname is not None:
                raise ValueError("global suppressions must not set tenant_id or hostname")
        elif self.scope == "tenant":
            if self.tenant_id is None:
                raise ValueError("tenant_id is required for tenant scope")
            if self.hostname is not None:
                raise ValueError("hostname must be null for tenant scope")
        elif self.scope == "host":
            if self.tenant_id is None:
                raise ValueError("tenant_id is required for host scope")
            if not self.hostname:
                raise ValueError("hostname is required for host scope")

        if self.match_process_path and not self.process_path_value:
            raise ValueError("process_path_value required when match_process_path is true")
        if self.match_parent_process and not self.parent_process_value:
            raise ValueError("parent_process_value required when match_parent_process is true")
        if self.match_file_hash and not self.file_hash_value:
            raise ValueError("file_hash_value required when match_file_hash is true")
        if self.match_hostname:
            if not self.hostname_value and not self.hostname:
                raise ValueError("hostname_value (or hostname) required when match_hostname is true")
            if not self.hostname_value and self.hostname:
                self.hostname_value = self.hostname
        return self


class SuppressionPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_at: Optional[datetime] = None
    reason: Optional[str] = Field(default=None, max_length=4000)
    disabled: Optional[bool] = None

    @model_validator(mode="after")
    def require_update(self) -> "SuppressionPatchRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "reason" in self.model_fields_set and self.reason is not None:
            self.reason = self.reason.strip() or None
        return self


class BulkAlertsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_ids: List[UUID] = Field(min_length=1, max_length=200)
    status: Optional[BulkAlertStatus] = None
    action: Optional[BulkAlertAction] = None
    reason: Optional[str] = Field(default=None, max_length=4000)
    create_suppressions: bool = True

    @model_validator(mode="after")
    def normalize(self) -> "BulkAlertsRequest":
        # Preserve order while de-duplicating.
        seen = set()
        unique: List[UUID] = []
        for aid in self.alert_ids:
            if aid not in seen:
                seen.add(aid)
                unique.append(aid)
        self.alert_ids = unique
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        if self.action == "approve_ai_low_priority":
            return self
        if self.status is None:
            raise ValueError(
                "status is required unless action=approve_ai_low_priority"
            )
        return self


class CustomerSuppressionCreateRequest(BaseModel):
  """Tenant-bound suppression create; tenant_id is forced from the URL short_code."""

  model_config = ConfigDict(extra="forbid")

  scope: Literal["tenant", "host"] = "tenant"
  rule_id: str = Field(min_length=1, max_length=128)
  hostname: Optional[str] = Field(default=None, max_length=255)
  match_process_path: bool = False
  process_path_value: Optional[str] = Field(default=None, max_length=1000)
  match_parent_process: bool = False
  parent_process_value: Optional[str] = Field(default=None, max_length=1000)
  match_file_hash: bool = False
  file_hash_value: Optional[str] = Field(default=None, max_length=128)
  match_hostname: bool = False
  hostname_value: Optional[str] = Field(default=None, max_length=255)
  expires_at: Optional[datetime] = None
  reason: Optional[str] = Field(default=None, max_length=4000)

  @model_validator(mode="after")
  def validate_customer_scope(self) -> "CustomerSuppressionCreateRequest":
    self.rule_id = self.rule_id.strip()
    if not self.rule_id:
      raise ValueError("rule_id cannot be blank")
    if self.hostname is not None:
      self.hostname = self.hostname.strip() or None
    if self.hostname_value is not None:
      self.hostname_value = self.hostname_value.strip() or None
    if self.process_path_value is not None:
      self.process_path_value = self.process_path_value.strip() or None
    if self.parent_process_value is not None:
      self.parent_process_value = self.parent_process_value.strip() or None
    if self.file_hash_value is not None:
      self.file_hash_value = self.file_hash_value.strip().lower() or None
    if self.reason is not None:
      self.reason = self.reason.strip() or None

    if self.scope == "tenant":
      self.hostname = None
    elif self.scope == "host" and not self.hostname:
      raise ValueError("hostname is required for host scope")

    if self.match_process_path and not self.process_path_value:
      raise ValueError("process_path_value required when match_process_path is true")
    if self.match_parent_process and not self.parent_process_value:
      raise ValueError("parent_process_value required when match_parent_process is true")
    if self.match_file_hash and not self.file_hash_value:
      raise ValueError("file_hash_value required when match_file_hash is true")
    if self.match_hostname:
      if not self.hostname_value and not self.hostname:
        raise ValueError("hostname_value (or hostname) required when match_hostname is true")
      if not self.hostname_value and self.hostname:
        self.hostname_value = self.hostname
    return self


class BulkIncidentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_ids: List[UUID] = Field(min_length=1, max_length=200)
    status: BulkIncidentStatus
    close_reason: BulkIncidentCloseReason

    @model_validator(mode="after")
    def normalize(self) -> "BulkIncidentsRequest":
        seen = set()
        unique: List[UUID] = []
        for iid in self.incident_ids:
            if iid not in seen:
                seen.add(iid)
                unique.append(iid)
        self.incident_ids = unique
        return self