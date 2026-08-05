"""Cloud→appliance channel inbox + appliance→cloud frame ingest."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.db.session import db_transaction, fetch_all, fetch_one
from app.services import appliance_jobs as appliance_jobs_service

logger = logging.getLogger(__name__)


def enqueue_frame(
    *,
    appliance_id: str,
    tenant_id: str,
    frame_type: str,
    payload: Dict[str, Any],
    frame_id: Optional[str] = None,
) -> Dict[str, Any]:
    fid = frame_id or str(uuid4())
    envelope = {
        "v": 1,
        "type": frame_type,
        "id": fid,
        "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "payload": payload,
    }
    with db_transaction() as cur:
        cur.execute(
            """
            INSERT INTO appliance_channel_inbox (
                id, appliance_id, tenant_id, frame_type, envelope
            )
            VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb)
            RETURNING id::text, frame_type, status, created_at::text;
            """,
            (fid, appliance_id, tenant_id, frame_type, json.dumps(envelope)),
        )
        row = cur.fetchone()
    return dict(row)


def claim_inbox(appliance_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    with db_transaction() as cur:
        cur.execute(
            """
            SELECT id FROM appliance_channel_inbox
            WHERE appliance_id = %s::uuid
              AND status = 'pending'
              AND expires_at > now()
            ORDER BY created_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED;
            """,
            (appliance_id, limit),
        )
        ids = [str(r["id"]) for r in (cur.fetchall() or [])]
        if not ids:
            return []
        cur.execute(
            """
            UPDATE appliance_channel_inbox
            SET status = 'delivered', delivered_at = now()
            WHERE id = ANY(%s::uuid[])
            RETURNING id::text, frame_type, envelope, created_at::text;
            """,
            (ids,),
        )
        rows = cur.fetchall() or []
    out = []
    for r in rows:
        env = r["envelope"]
        if isinstance(env, str):
            env = json.loads(env)
        out.append(env)
    return out


def ack_frame(appliance_id: str, frame_id: str, *, success: bool = True) -> bool:
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE appliance_channel_inbox
            SET status = %s, acked_at = now()
            WHERE id = %s::uuid AND appliance_id = %s::uuid
            RETURNING id;
            """,
            ("acked" if success else "failed", frame_id, appliance_id),
        )
        return cur.fetchone() is not None


def store_outbound(appliance_id: str, tenant_id: str, envelope: Dict[str, Any]) -> str:
    frame_type = str(envelope.get("type") or "status")
    with db_transaction() as cur:
        cur.execute(
            """
            INSERT INTO appliance_channel_outbound (
                appliance_id, tenant_id, frame_type, envelope
            )
            VALUES (%s::uuid, %s::uuid, %s, %s::jsonb)
            RETURNING id::text;
            """,
            (appliance_id, tenant_id, frame_type, json.dumps(envelope)),
        )
        return cur.fetchone()["id"]


def poll_bundle(appliance_id: str, tenant_id: str) -> Dict[str, Any]:
    """Return channel inbox frames + pending appliance_jobs as job frames."""
    frames = claim_inbox(appliance_id)
    # Also surface pending AR jobs as channel "job" frames for channeld consumers
    try:
        jobs = appliance_jobs_service.claim_pending_jobs(appliance_id, limit=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("channel poll job claim failed: %s", exc)
        jobs = []
    for job in jobs:
        frames.append(
            {
                "v": 1,
                "type": "job",
                "id": job.get("id"),
                "ts": job.get("created_at"),
                "tenant_id": tenant_id,
                "payload": {
                    "job_id": job.get("id"),
                    "job_type": job.get("job_type"),
                    "edr_execution_id": job.get("edr_execution_id"),
                    **(job.get("payload") or {}),
                },
            }
        )
    return {"frames": frames, "count": len(frames)}
