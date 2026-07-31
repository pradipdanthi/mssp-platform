"""KB-083/084: EDR / MXDR API models."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

EdrActionType = Literal[
    "ISOLATE_HOST",
    "UNISOLATE_HOST",
    "KILL_PROCESS",
    "COLLECT_FORENSICS",
    "BLOCK_HASH",
]
# Lifecycle: PENDING -> EXECUTING -> SUCCESS/FAILED -> VERIFIED (+ legacy executed)
EdrActionStatus = Literal[
    "pending",
    "executing",
    "success",
    "failed",
    "verified",
    "executed",
]


class ProcessTreeNode(BaseModel):
    pid: Optional[int] = None
    parent_pid: Optional[int] = None
    process_guid: Optional[str] = None
    parent_process_guid: Optional[str] = None
    process_name: Optional[str] = None
    parent_process_name: Optional[str] = None
    command_line: Optional[str] = None
    parent_command_line: Optional[str] = None
    user: Optional[str] = None
    hash_md5: Optional[str] = None
    hash_sha256: Optional[str] = None
    signed_status: Optional[str] = None
    mitre_techniques: List[str] = Field(default_factory=list)
    event_time: Optional[str] = None
    child_processes: List["ProcessTreeNode"] = Field(default_factory=list)


ProcessTreeNode.model_rebuild()


class ProcessTreeResponse(BaseModel):
    incident_id: Optional[str] = None
    alert_id: Optional[str] = None
    root: Optional[ProcessTreeNode] = None
    events_considered: int = 0
    message: Optional[str] = None


class EdrActionExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: EdrActionType
    tenant_short_code: Optional[str] = Field(default=None, max_length=32)
    incident_id: Optional[str] = None
    incident_number: Optional[str] = None
    alert_id: Optional[str] = None
    agent_id: Optional[str] = Field(default=None, max_length=64)
    pid: Optional[int] = Field(default=None, ge=1, le=2_147_483_647)
    file_hash_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    confirm_isolation: bool = False
    retry_of_execution_id: Optional[str] = None


class EdrActionExecuteResponse(BaseModel):
    execution_id: str
    status: EdrActionStatus
    message: str
    upload_url: Optional[str] = None
    forensic_artifact_id: Optional[str] = None


class EdrActionStatusResponse(BaseModel):
    execution_id: str
    status: EdrActionStatus
    action_type: EdrActionType
    result_message: Optional[str] = None
    status_detail: Optional[str] = None
    verified_at: Optional[str] = None
    download_url: Optional[str] = None
    forensic_artifact_id: Optional[str] = None
    created_at: str
    updated_at: str


class EdrActionCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    execution_id: str
    status: Literal["executing", "success", "failed", "timeout"]
    message: Optional[str] = Field(default=None, max_length=2000)
    error_log: Optional[str] = Field(default=None, max_length=8000)
    agent_id: Optional[str] = Field(default=None, max_length=64)
    external_ref: Optional[str] = Field(default=None, max_length=255)
    # Endpoint-proven quarantine flag (KB-091 Wave 1). True → isolate Verified.
    applied: Optional[bool] = None
    # Auto-release / unisolate callback: clear edr_endpoint_isolation to restored.
    released: Optional[bool] = None


class EdrForensicsCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: Optional[str] = None
    execution_id: Optional[str] = None
    tenant_id: Optional[str] = None
    tenant_short_code: Optional[str] = Field(default=None, max_length=32)
    endpoint_id: Optional[str] = Field(default=None, max_length=64)
    file_size_bytes: Optional[int] = Field(default=None, ge=0)
    sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    object_key: Optional[str] = None
    status: Literal["uploaded", "failed"] = "uploaded"
    message: Optional[str] = Field(default=None, max_length=2000)


class ForensicArtifactPublic(BaseModel):
    artifact_id: str
    status: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    download_url: Optional[str] = None
    created_at: str


class MitreMappingPublic(BaseModel):
    tactics: List[str] = Field(default_factory=list)
    techniques: List[Dict[str, str]] = Field(default_factory=list)


class EdrIncidentDeepDiveResponse(BaseModel):
    incident_number: str
    endpoint: Dict[str, Any]
    mitre: MitreMappingPublic
    process_tree: ProcessTreeResponse
    recent_actions: List[EdrActionStatusResponse] = Field(default_factory=list)
    forensic_artifacts: List[ForensicArtifactPublic] = Field(default_factory=list)


class EdrMetricsSummary(BaseModel):
    mean_time_to_contain_seconds: Optional[float] = None
    telemetry_events_processed: int = 0
    isolated_endpoints_count: int = 0
