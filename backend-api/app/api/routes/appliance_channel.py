"""
KB-093 Track-4: Appliance channel gateway (Phase B).

- WebSocket: /appliance/v1/channel
- HTTPS poll fallback: GET /appliance/channel/poll
- Appliance→cloud frames: POST /appliance/channel/frames
- Enqueue OTA/license frames: POST /appliance/channel/enqueue (admin JWT via separate router later;
  appliance-facing enqueue for cloud workers uses service path below for jobs already in DB)

Auth: X-Appliance-ID + X-Appliance-API-Key (same as heartbeat). Optional client cert
is terminated at the edge in production Appliance Management plane.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ConfigDict, Field

from app.services.appliance_auth_service import (
    ApplianceRetiredError,
    InvalidApplianceCredentialsError,
    verify_appliance_credentials,
)
from app.services import appliance_channel as channel_service
from app.services import appliance_jobs as appliance_jobs_service
from app.services.edr_actions import apply_action_callback
from app.db.session import fetch_one

logger = logging.getLogger(__name__)

router = APIRouter(tags=["appliance-channel"])


def _auth_appliance(appliance_id: Optional[str], api_key: Optional[str]) -> Dict[str, Any]:
    if not appliance_id or not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing appliance credentials")
    try:
        UUID(appliance_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid appliance credentials") from exc
    try:
        return verify_appliance_credentials(appliance_id, api_key)
    except InvalidApplianceCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid appliance credentials") from exc
    except ApplianceRetiredError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Appliance is retired") from exc


class ChannelFrameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: int = 1
    type: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=64)
    ts: Optional[str] = None
    tenant_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    sig: Optional[str] = None


class ChannelFramesBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frames: list[ChannelFrameIn] = Field(default_factory=list, max_length=100)


class ChannelEnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_type: str = Field(min_length=1, max_length=64)
    payload: Dict[str, Any] = Field(default_factory=dict)


@router.get("/appliance/channel/poll")
def channel_poll(
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
) -> Dict[str, Any]:
    appliance = _auth_appliance(x_appliance_id, x_appliance_api_key)
    bundle = channel_service.poll_bundle(appliance["id"], appliance["tenant_id"])
    return {"ok": True, **bundle}


@router.post("/appliance/channel/frames")
def channel_frames_in(
    body: ChannelFramesBatch,
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
) -> Dict[str, Any]:
    appliance = _auth_appliance(x_appliance_id, x_appliance_api_key)
    stored = 0
    for frame in body.frames:
        env = frame.model_dump()
        channel_service.store_outbound(appliance["id"], appliance["tenant_id"], env)
        stored += 1
        # Handle acks for inbox / job completion
        if frame.type == "ack":
            payload = frame.payload or {}
            ref = str(payload.get("ref") or payload.get("frame_id") or "")
            if ref:
                channel_service.ack_frame(appliance["id"], ref, success=bool(payload.get("success", True)))
            job_id = payload.get("job_id")
            if job_id:
                row = appliance_jobs_service.complete_job(
                    job_id=str(job_id),
                    appliance_id=appliance["id"],
                    success=bool(payload.get("success", True)),
                    result=payload.get("result"),
                    message=str(payload.get("message") or ""),
                )
                if row and row.get("edr_execution_id"):
                    try:
                        apply_action_callback(
                            execution_id=row["edr_execution_id"],
                            status="success" if payload.get("success", True) else "failed",
                            message=str(payload.get("message") or ""),
                            payload=payload.get("result") or {},
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("channel job ack EDR callback failed: %s", exc)
    return {"ok": True, "stored": stored}


@router.post("/appliance/channel/enqueue")
def channel_enqueue(
    body: ChannelEnqueueRequest,
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
) -> Dict[str, Any]:
    """
    Restricted: only used by trusted automation with appliance credentials
    for loopback tests. Production OTA/license push uses admin routes.
    """
    appliance = _auth_appliance(x_appliance_id, x_appliance_api_key)
    # Appliances should not enqueue arbitrary control to themselves in prod;
    # allow only ack-related test types is safer — keep for factory smoke.
    if body.frame_type not in ("control", "ota.offer", "license.push", "job"):
        raise HTTPException(status_code=400, detail="unsupported frame_type")
    row = channel_service.enqueue_frame(
        appliance_id=appliance["id"],
        tenant_id=appliance["tenant_id"],
        frame_type=body.frame_type,
        payload=body.payload,
    )
    return {"ok": True, "frame": row}


@router.websocket("/appliance/v1/channel")
async def appliance_channel_ws(websocket: WebSocket) -> None:
    import asyncio

    await websocket.accept()
    appliance_id = websocket.headers.get("x-appliance-id") or websocket.query_params.get("appliance_id")
    api_key = websocket.headers.get("x-appliance-api-key") or websocket.query_params.get("api_key")
    try:
        appliance = _auth_appliance(appliance_id, api_key)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await websocket.send_json(
        {
            "v": 1,
            "type": "control",
            "id": "session-hello",
            "payload": {"message": "channel connected", "appliance_id": appliance["id"]},
        }
    )

    try:
        while True:
            bundle = channel_service.poll_bundle(appliance["id"], appliance["tenant_id"])
            for frame in bundle.get("frames") or []:
                await websocket.send_json(frame)

            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=15.0)
            except asyncio.TimeoutError:
                # keepalive ping from server
                await websocket.send_json(
                    {
                        "v": 1,
                        "type": "heartbeat",
                        "id": "server-ping",
                        "payload": {"ping": True},
                    }
                )
                continue
            except WebSocketDisconnect:
                break

            if not isinstance(data, dict):
                continue
            ftype = data.get("type")
            if ftype == "heartbeat":
                channel_service.store_outbound(appliance["id"], appliance["tenant_id"], data)
                await websocket.send_json(
                    {"v": 1, "type": "ack", "id": data.get("id"), "payload": {"ok": True}}
                )
            elif ftype == "ack":
                payload = data.get("payload") or {}
                ref = str(payload.get("ref") or "")
                if ref:
                    channel_service.ack_frame(
                        appliance["id"], ref, success=bool(payload.get("success", True))
                    )
                job_id = payload.get("job_id")
                if job_id:
                    appliance_jobs_service.complete_job(
                        job_id=str(job_id),
                        appliance_id=appliance["id"],
                        success=bool(payload.get("success", True)),
                        result=payload.get("result"),
                        message=str(payload.get("message") or ""),
                    )
            else:
                channel_service.store_outbound(appliance["id"], appliance["tenant_id"], data)
    except WebSocketDisconnect:
        logger.info("appliance channel disconnected %s", appliance.get("id"))
    except Exception:
        logger.exception("appliance channel error")
        try:
            await websocket.close()
        except Exception:
            pass
