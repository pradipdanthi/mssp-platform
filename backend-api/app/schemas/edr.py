"""KB-083/084: EDR / MXDR API models."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    # Live image name (e.g. notepad.exe). Preferred over pid — resolved on the endpoint.
    process_name: Optional[str] = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9._\-]+$")
    file_hash_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    confirm_isolation: bool = False
    retry_of_execution_id: Optional[str] = None
    # When true with process_name: enumerate live matches on endpoint (no kill).
    list_only: bool = False

    @model_validator(mode="after")
    def _kill_target_required(self) -> "EdrActionExecuteRequest":
        if self.action_type != "KILL_PROCESS":
            return self
        if self.list_only and not self.process_name:
            raise ValueError("process_name is required when list_only=true")
        if self.pid is None and not self.process_name:
            raise ValueError("pid or process_name is required for KILL_PROCESS")
        return self


class LiveProcessInfo(BaseModel):
    pid: int
    name: Optional[str] = None
    path: Optional[str] = None


class LiveProcessesResponse(BaseModel):
    agent_id: str
    process_name: str
    execution_id: str
    status: EdrActionStatus
    processes: List[LiveProcessInfo] = Field(default_factory=list)
    message: Optional[str] = None
    source: str = "endpoint_live"
    # Present when falling back to Wazuh syscollector (may be stale).
    scan_time: Optional[str] = None
    stale: bool = False


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
    callback_payload: Optional[Dict[str, Any]] = None


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
