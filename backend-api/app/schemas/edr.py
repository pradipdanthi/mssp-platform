"""KB-083: EDR / MXDR API models."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

EdrActionType = Literal["ISOLATE_HOST", "KILL_PROCESS", "COLLECT_FORENSICS", "BLOCK_HASH"]
EdrActionStatus = Literal["pending", "executed", "failed"]


class ProcessTreeNode(BaseModel):
    pid: Optional[int] = None
    parent_pid: Optional[int] = None
    process_name: Optional[str] = None
    command_line: Optional[str] = None
    user: Optional[str] = None
    hash_sha256: Optional[str] = None
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


class EdrActionExecuteResponse(BaseModel):
    execution_id: str
    status: EdrActionStatus
    message: str


class EdrActionStatusResponse(BaseModel):
    execution_id: str
    status: EdrActionStatus
    action_type: EdrActionType
    result_message: Optional[str] = None
    created_at: str
    updated_at: str


class MitreMappingPublic(BaseModel):
    tactics: List[str] = Field(default_factory=list)
    techniques: List[Dict[str, str]] = Field(default_factory=list)


class EdrIncidentDeepDiveResponse(BaseModel):
    incident_number: str
    endpoint: Dict[str, Any]
    mitre: MitreMappingPublic
    process_tree: ProcessTreeResponse
    recent_actions: List[EdrActionStatusResponse] = Field(default_factory=list)


class EdrMetricsSummary(BaseModel):
    mean_time_to_contain_seconds: Optional[float] = None
    telemetry_events_processed: int = 0
    isolated_endpoints_count: int = 0
