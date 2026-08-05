"""Local appliance REST surface for catalogue jobs (LAN-only / loopback).

Exposes junexis-engine-api endpoints used by svc-02..10 workers and cloud-pushed jobs.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from appliance.hunting.retrospective_sweeper import RetrospectiveSweeper
from appliance.jobs import queue as job_queue
from appliance.jobs.executor import execute_job


SVC_FOR_JOB_TYPE = {
    "ir": "svc-02",
    "incident_response": "svc-02",
    "collect_evidence": "svc-02",
    "containment": "svc-03",
    "isolate": "svc-03",
    "active_response": "svc-03",
    "hunt": "svc-07",
    "ioc_push": "svc-07",
    "cache_push": "svc-07",
    "retrospective-hunt": "svc-07",
    "forensics": "svc-08",
    "easm": "svc-09",
    "nuclei_scan": "svc-09",
    "itdr": "svc-10",
    "identity_sync": "svc-10",
}


class ApplianceAPIHandler(BaseHTTPRequestHandler):
    sweeper = RetrospectiveSweeper()

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter
        return

    def _json(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("invalid json") from exc

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in {"/health", "/appliance/v1/health"}:
            self._json(
                200,
                {
                    "status": "ok",
                    "service": "junexis-engine-api",
                    "capabilities": sorted(set(SVC_FOR_JOB_TYPE.values())),
                },
            )
            return

        if path.startswith("/appliance/v1/jobs/retrospective-hunt/"):
            job_id = path.rsplit("/", 1)[-1]
            job = self.sweeper.get_job(job_id)
            if not job:
                # fall back to local queue
                job = job_queue.get_job(job_id)
            if not job:
                self._json(404, {"detail": "job not found"})
                return
            self._json(200, job)
            return

        if path.startswith("/appliance/v1/jobs/") and path.count("/") == 4:
            job_id = path.rsplit("/", 1)[-1]
            job = job_queue.get_job(job_id)
            if not job:
                self._json(404, {"detail": "job not found"})
                return
            self._json(200, job)
            return

        if path == "/appliance/v1/jobs":
            svc = (qs.get("svc") or [None])[0]
            self._json(200, {"jobs": job_queue.list_jobs(svc)})
            return

        if path == "/appliance/v1/jobs/claim":
            # GET claim?svc=svc-02&worker_id=...
            svc = (qs.get("svc") or [""])[0]
            worker_id = (qs.get("worker_id") or ["worker"])[0]
            if not svc:
                self._json(400, {"detail": "svc required"})
                return
            job = job_queue.claim_next(svc, worker_id=worker_id)
            self._json(200, {"job": job})
            return

        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except ValueError:
            self._json(400, {"detail": "invalid json"})
            return

        if path == "/appliance/v1/jobs/retrospective-hunt":
            try:
                result = self.sweeper.run_job(payload)
                # also record in local queue for visibility
                job_queue.enqueue(
                    svc="svc-07",
                    job_type="retrospective-hunt",
                    payload=payload,
                    job_id=payload.get("job_id"),
                )
                self._json(200, result)
            except ValueError as exc:
                self._json(400, {"detail": str(exc)})
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"detail": str(exc)})
            return

        if path == "/appliance/v1/jobs":
            job_type = str(payload.get("job_type") or payload.get("type") or "").strip()
            svc = str(payload.get("svc") or SVC_FOR_JOB_TYPE.get(job_type) or "").strip()
            if not svc or not job_type:
                self._json(400, {"detail": "svc and job_type required"})
                return
            body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
            queued = job_queue.enqueue(
                svc=svc,
                job_type=job_type,
                payload=body,
                cloud_job_id=payload.get("cloud_job_id"),
                job_id=payload.get("job_id"),
            )
            # Optional sync execute for small jobs
            if payload.get("execute_now"):
                ok, result = execute_job(svc, job_type, body)
                job_queue.complete(queued["job_id"], success=ok, result=result)
                queued["status"] = "success" if ok else "failed"
                queued["result"] = result
            self._json(200, queued)
            return

        if path.startswith("/appliance/v1/jobs/") and path.endswith("/complete"):
            job_id = path.split("/")[-2]
            ok = bool(payload.get("success", True))
            job_queue.complete(job_id, success=ok, result=payload.get("result") or {})
            self._json(200, {"job_id": job_id, "status": "success" if ok else "failed"})
            return

        if path.startswith("/appliance/v1/jobs/") and path.endswith("/execute"):
            job_id = path.split("/")[-2]
            job = job_queue.get_job(job_id)
            if not job:
                self._json(404, {"detail": "job not found"})
                return
            ok, result = execute_job(job["svc"], job["job_type"], job.get("payload") or {})
            job_queue.complete(job_id, success=ok, result=result)
            self._json(200, {"job_id": job_id, "success": ok, "result": result})
            return

        self._json(404, {"detail": "not found"})


def serve(host: str | None = None, port: int | None = None) -> None:
    """
    Bind loopback by default — cloud reaches this via outbound channel / job push,
    not a public inbound WAN port (KB-093 locked posture).
    """
    host = host or os.environ.get("JUNEXIS_ENGINE_API_HOST", "127.0.0.1")
    port = int(port or os.environ.get("JUNEXIS_ENGINE_API_PORT", "8787"))
    job_queue.write_status_marker()
    httpd = ThreadingHTTPServer((host, port), ApplianceAPIHandler)
    print(f"junexis-engine-api on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
