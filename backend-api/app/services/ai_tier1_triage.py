"""
Tier-1 AI SOC Triage Copilot — on-demand Ollama chat with structured JSON.

Frontends call control-plane APIs only; this service proxies to Ollama
POST /api/chat (native) with format schema, 8s timeout, and DB cache.

Phase 1: live DB enrichment (assets, TI IOC match, related alerts ±60s,
prior FP / suppressions, signature if present) grounded into the prompt as
FACTS. Never invents VirusTotal / external reputation. Never auto-closes.

Phase 2: grounded pattern memory (rule/process FP), deterministic pre_score
hints, recommendation guardrails + queue_suggestion metadata, optional
gated VT hash lookup. Still never auto-executes close/suppress/isolate.

Phase 3: persist ai_verdict/ai_confidence/ai_queue for list filters; VT stats
in enrichment (server-side key only); OPT-IN auto-close via
ENABLE_AUTO_CLOSE_LOW_RISK (default false) with hard severity/level guards.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.secrets import read_secret
from app.db.session import fetch_all, fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(
    r"(?i)(password|passwd|api[_-]?key|token|secret|authorization|bearer)\s*[:=]\s*\S+"
)

RELATED_WINDOW_SECONDS = 60
ENRICHMENT_LIST_LIMIT = 8
VT_TIMEOUT_SECONDS = 2.0
# Low-priority / AI Reviewed queue: BENIGN_FALSE_POSITIVE + confidence threshold.
LOW_PRIORITY_CONFIDENCE_MIN = 85.0
# Auto-close (opt-in) requires higher confidence than queue routing.
AUTO_CLOSE_CONFIDENCE_MIN = 95.0
AI_RESOLUTION_AUTO_CLOSE = "Closed (AI Auto-Triage)"

SYSTEM_PROMPT = (
    "You are a Senior Cyber Threat Analyst specializing in Windows Security, "
    "Sysmon, and Enterprise Telemetry Triage.\n"
    "Your task is to analyze telemetry events and determine if an alert is "
    "benign administrative noise or genuine threat behavior.\n"
    "CRITICAL: You MUST evaluate Process Name, Path, Parent Process, "
    "CommandLine, and User context together.\n"
    "Never declare a process benign based on name alone if it executes from "
    "Temp, User Profile, or un-signed directories.\n"
    "GROUNDING RULES:\n"
    "- Base conclusions only on Telemetry and the FACTS block provided.\n"
    "- If signature status, hash reputation, or VirusTotal is unknown / "
    "not_configured, say unknown — do NOT invent external intel.\n"
    "- Prior false-positive / suppression history is a signal, not proof.\n"
    "- When FACTS.action_guardrails.historical_fp_pressure is 'high' and "
    "there is no TI hit and no high-risk path/cmdline hints, bias toward "
    "AUTO_SUPPRESS (human-confirmed suppression only).\n"
    "- When FACTS show TI hit, encoded PowerShell, or unexpected LOLBin "
    "path, bias away from AUTO_SUPPRESS toward INVESTIGATE_HOST or "
    "ISOLATE_AGENT.\n"
    "- recommended_action AUTO_SUPPRESS means suggest a human-confirmed "
    "suppression rule only — never imply the system will silently close alerts.\n"
    "- Do not invent queue routing or auto-containment; queue_suggestion is "
    "metadata only."
)

VERDICTS = frozenset({"BENIGN_FALSE_POSITIVE", "SUSPICIOUS", "MALICIOUS"})
ACTIONS = frozenset({"AUTO_SUPPRESS", "INVESTIGATE_HOST", "ISOLATE_AGENT"})

JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": sorted(VERDICTS),
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
        "recommended_action": {
            "type": "string",
            "enum": sorted(ACTIONS),
        },
        "suggested_suppression_scope": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string"},
                "process_path": {"type": "string"},
                "justification": {"type": "string"},
            },
            "required": ["rule_id", "process_path", "justification"],
        },
    },
    "required": [
        "verdict",
        "confidence",
        "summary",
        "recommended_action",
        "suggested_suppression_scope",
    ],
}

# Strict wall-clock for Ollama — never block dashboard list paths.
DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_NUM_THREAD = 2
DEFAULT_NUM_PREDICT = 128
DEFAULT_NUM_CTX = 2048

_SIGNED_PATH_HINTS = (
    "\\windows\\system32\\",
    "\\windows\\syswow64\\",
    "/usr/bin/",
    "/usr/sbin/",
    "/bin/",
    "/sbin/",
)

_EXPECTED_SYSTEM_PATH_MARKERS = (
    "\\windows\\system32\\",
    "\\windows\\syswow64\\",
    "\\windows\\system32\\windowspowershell\\",
    "\\windows\\syswow64\\windowspowershell\\",
    "\\program files\\",
    "\\program files (x86)\\",
    "/usr/bin/",
    "/usr/sbin/",
    "/bin/",
    "/sbin/",
)

_TEMP_OR_PROFILE_MARKERS = (
    "\\temp\\",
    "\\tmp\\",
    "/temp/",
    "/tmp/",
    "\\appdata\\local\\temp\\",
    "\\appdata\\roaming\\",
    "\\users\\",
    "/home/",
    "\\downloads\\",
    "\\desktop\\",
    "\\public\\",
)

_LOLBIN_NAMES = frozenset(
    {
        "powershell.exe",
        "pwsh.exe",
        "cmd.exe",
        "wscript.exe",
        "cscript.exe",
        "mshta.exe",
        "rundll32.exe",
        "regsvr32.exe",
        "certutil.exe",
        "bitsadmin.exe",
        "msiexec.exe",
        "dllhost.exe",
        "svchost.exe",
        "taskhost.exe",
        "taskhostw.exe",
        "cmstp.exe",
        "installutil.exe",
        "msbuild.exe",
        "csi.exe",
        "forfiles.exe",
        "hh.exe",
    }
)

_CMDLINE_RED_FLAGS = (
    "-enc ",
    "-encodedcommand",
    "-e ",
    "frombase64string",
    "downloadstring",
    "downloadfile",
    "iex(",
    "invoke-expression",
    "invoke-webrequest",
    "bypass",
    "-nop",
    "-noprofile",
    "-w hidden",
    "-windowstyle hidden",
    "hidden",
    "javascript:",
    "vbscript:",
)


def _redact(text: str, limit: int = 2000) -> str:
    cleaned = _SECRET_RE.sub(r"\1=[REDACTED]", text or "")
    cleaned = re.sub(r"\b[A-Za-z0-9_\-]{32,}\b", "[REDACTED_TOKEN]", cleaned)
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def _ollama_root() -> str:
    base = (os.getenv("AI_ALERT_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("AI_ALERT_BASE_URL not configured")
    # OpenAI-compat URLs end with /v1; native chat is at host root /api/chat.
    if base.endswith("/v1"):
        return base[: -len("/v1")].rstrip("/")
    if base.endswith("/chat/completions"):
        # strip .../v1/chat/completions → host
        without = base[: -len("/chat/completions")].rstrip("/")
        if without.endswith("/v1"):
            return without[: -len("/v1")].rstrip("/")
        return without
    return base


def _timeout_seconds() -> float:
    raw = (os.getenv("AI_TIER1_TRIAGE_TIMEOUT_SECONDS") or str(DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        val = float(raw)
    except ValueError:
        val = float(DEFAULT_TIMEOUT_SECONDS)
    # Default product target is 8s; allow higher for slow local LLMs (cap 120s).
    return max(1.0, min(val, 120.0))


def _num_thread() -> int:
    raw = (
        os.getenv("OLLAMA_CPU_THREADS")
        or os.getenv("AI_TIER1_NUM_THREAD")
        or str(DEFAULT_NUM_THREAD)
    ).strip()
    try:
        return max(1, min(int(raw), 32))
    except ValueError:
        return DEFAULT_NUM_THREAD


def _num_predict() -> int:
    raw = (os.getenv("AI_TIER1_NUM_PREDICT") or str(DEFAULT_NUM_PREDICT)).strip()
    try:
        return max(16, min(int(raw), 512))
    except ValueError:
        return DEFAULT_NUM_PREDICT


def _num_ctx() -> int:
    raw = (os.getenv("AI_TIER1_NUM_CTX") or str(DEFAULT_NUM_CTX)).strip()
    try:
        return max(512, min(int(raw), 8192))
    except ValueError:
        return DEFAULT_NUM_CTX


def _keep_alive() -> str:
    return (os.getenv("OLLAMA_KEEP_ALIVE") or "30m").strip() or "30m"


def build_content_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_triage_payload_from_alert(
    alert: Dict[str, Any], *, customer_safe: bool = False
) -> Dict[str, Any]:
    """Stable fields used for prompt + cache key (exclude volatile timestamps)."""
    fields = _resolve_process_fields(alert)
    payload: Dict[str, Any] = {
        "alert_title": alert.get("alert_title") or alert.get("title"),
        "severity": alert.get("severity"),
        "wazuh_rule_id": alert.get("wazuh_rule_id") or fields.get("wazuh_rule_id"),
        "process_name": alert.get("process_name") or fields.get("process_name"),
        "file_path": alert.get("file_path") or fields.get("file_path"),
        "parent_process_name": alert.get("parent_process_name")
        or fields.get("parent_process_name"),
        "command_line": alert.get("command_line") or fields.get("command_line"),
        "parent_command_line": alert.get("parent_command_line")
        or fields.get("parent_command_line"),
        "source_user": alert.get("source_user") or fields.get("source_user"),
        "hostname": alert.get("hostname")
        or alert.get("asset_hostname")
        or alert.get("destination_host"),
        "hash_sha256": alert.get("hash_sha256") or fields.get("hash_sha256"),
        "hash_md5": alert.get("hash_md5") or fields.get("hash_md5"),
        "mitre_tactics": alert.get("mitre_tactics") or [],
        "mitre_techniques": alert.get("mitre_techniques") or [],
        "description": alert.get("alert_description") or alert.get("description"),
    }
    if customer_safe:
        # No IPs, raw_event, external ids, or internal AI drafts.
        payload.pop("source_user", None)
        return {k: v for k, v in payload.items() if v not in (None, "", [])}
    # Admin may include source IP lightly (redacted in prompt).
    payload["source_ip"] = alert.get("source_ip")
    payload["source_tool"] = alert.get("source_tool") or alert.get("source")
    return {k: v for k, v in payload.items() if v not in (None, "", [])}


def _parse_event_time(alert: Dict[str, Any]) -> Optional[datetime]:
    raw = alert.get("event_time") or alert.get("detected_at")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _basename(path_or_name: str) -> str:
    text = _normalize_win_path(path_or_name)
    if not text:
        return ""
    return text.rsplit("/", 1)[-1].strip().lower()


def _normalize_win_path(path_or_name: str) -> str:
    """Collapse escaped backslashes from JSON/message payloads for matching."""
    text = str(path_or_name or "").strip()
    if not text:
        return ""
    # Raw JSON often stores "C:\\\\Windows\\\\..." → normalize to single separators.
    while "\\\\" in text:
        text = text.replace("\\\\", "\\")
    return text.replace("\\", "/").lower()


def _parse_message_kv(message: str) -> Dict[str, str]:
    """Parse Sysmon-style 'Key: Value' lines from Windows event message text."""
    out: Dict[str, str] = {}
    if not message:
        return out
    for line in str(message).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().strip('"')
        val = val.strip().strip('"')
        if key and val and key not in out:
            out[key] = val
    return out


def _resolve_process_fields(alert: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Best-effort process/path/cmdline/user/hash from alert columns + raw_event.
    Falls back to Sysmon message KV when structured eventdata is empty.
    """
    from app.services.soc_alert_synthesis import (
        _eventdata_from_raw,
        _raw_dict,
        extract_wazuh_rule_id,
    )

    raw = _raw_dict(alert) if alert.get("raw_event") is not None else {}
    eventdata = _eventdata_from_raw(raw) if raw else {}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    system = win.get("system") if isinstance(win.get("system"), dict) else {}
    msg_kv = _parse_message_kv(str(system.get("message") or ""))

    def _pick(*vals: Any) -> Optional[str]:
        for v in vals:
            if v is None:
                continue
            text = str(v).strip()
            if text:
                return text
        return None

    process_path = _pick(
        alert.get("process_name"),
        alert.get("file_path"),
        eventdata.get("Image"),
        eventdata.get("image"),
        eventdata.get("process_name"),
        data.get("process_name"),
        msg_kv.get("Image"),
        msg_kv.get("Process Name"),
    )
    file_path = _pick(
        alert.get("file_path"),
        eventdata.get("TargetFilename"),
        eventdata.get("targetFilename"),
        eventdata.get("FilePath"),
        msg_kv.get("TargetFilename"),
        msg_kv.get("FileName"),
    )
    parent = _pick(
        alert.get("parent_process_name"),
        eventdata.get("ParentImage"),
        eventdata.get("parentImage"),
        msg_kv.get("ParentImage"),
        msg_kv.get("Parent Process Name"),
    )
    cmdline = _pick(
        alert.get("command_line"),
        eventdata.get("CommandLine"),
        eventdata.get("commandLine"),
        msg_kv.get("CommandLine"),
    )
    parent_cmdline = _pick(
        alert.get("parent_command_line"),
        eventdata.get("ParentCommandLine"),
        eventdata.get("parentCommandLine"),
        msg_kv.get("ParentCommandLine"),
    )
    user = _pick(
        alert.get("source_user"),
        eventdata.get("User"),
        msg_kv.get("User"),
    )
    hash_sha256 = _pick(alert.get("hash_sha256"), eventdata.get("Sha256"), eventdata.get("sha256"))
    hash_md5 = _pick(alert.get("hash_md5"), eventdata.get("Md5"), eventdata.get("md5"))
    hashes_blob = _pick(eventdata.get("Hashes"), eventdata.get("hashes"), msg_kv.get("Hashes"))
    if hashes_blob and (not hash_sha256 or not hash_md5):
        for part in hashes_blob.split(","):
            piece = part.strip()
            if "=" in piece:
                k, v = piece.split("=", 1)
                k = k.strip().lower()
                v = v.strip().lower()
                if k == "sha256" and len(v) == 64 and not hash_sha256:
                    hash_sha256 = v
                if k == "md5" and len(v) == 32 and not hash_md5:
                    hash_md5 = v

    # Title often embeds process basename: "Sysmon - Suspicious Process - dllhost.exe"
    title = str(alert.get("alert_title") or alert.get("title") or "")
    title_proc = None
    m = re.search(r"(?i)\b([a-z0-9_\-]+\.exe)\b", title)
    if m:
        title_proc = m.group(1)

    process_name = _basename(process_path or "") or (title_proc or None)
    rule_id = _pick(alert.get("wazuh_rule_id"), extract_wazuh_rule_id(raw) if raw else None)

    return {
        "process_path": process_path,
        "process_name": process_name,
        "file_path": file_path,
        "parent_process_name": parent,
        "command_line": cmdline,
        "parent_command_line": parent_cmdline,
        "source_user": user,
        "hash_sha256": hash_sha256,
        "hash_md5": hash_md5,
        "wazuh_rule_id": rule_id,
        "signature_raw": _pick(
            eventdata.get("Signed"),
            eventdata.get("signed"),
            eventdata.get("SignatureStatus"),
            eventdata.get("signature_status"),
            eventdata.get("Signature"),
            eventdata.get("SigStatus"),
            eventdata.get("AuthenticodeStatus"),
            msg_kv.get("Signed"),
            msg_kv.get("SignatureStatus"),
            msg_kv.get("Signature"),
            msg_kv.get("SigStatus"),
        ),
        "signature_extra": _pick(
            eventdata.get("Signature"),
            eventdata.get("Company"),
            msg_kv.get("Signature"),
            msg_kv.get("Company"),
        ),
    }


def _extract_signature_status(alert: Dict[str, Any]) -> Dict[str, str]:
    """Best-effort signature from raw_event; never invents VT/reputation."""
    fields = _resolve_process_fields(alert)
    explicit = fields.get("signature_raw")
    if explicit is not None and str(explicit).strip():
        val = str(explicit).strip().lower()
        if val in ("signed", "valid", "trusted", "true", "1", "yes", "valid_signature"):
            return {"status": "signed", "source": "raw_event"}
        if val in (
            "unsigned",
            "invalid",
            "untrusted",
            "false",
            "0",
            "no",
            "invalid_signature",
            "expired",
        ):
            return {"status": "unsigned", "source": "raw_event"}
        # Unknown Authenticode wording — surface as unknown, do not invent.
        return {"status": "unknown", "source": "raw_event_unparsed", "raw": val[:80]}

    path = _normalize_win_path(
        str(fields.get("process_path") or fields.get("file_path") or "")
    )
    if path:
        for hint in _SIGNED_PATH_HINTS:
            if hint.replace("\\", "/") in path:
                return {"status": "likely_signed_path", "source": "path_hint"}
    return {"status": "unknown", "source": "unavailable"}


def _admin_activity_signals(alert: Dict[str, Any]) -> List[str]:
    signals: List[str] = []
    fields = _resolve_process_fields(alert)
    user = str(fields.get("source_user") or alert.get("source_user") or "").strip().lower()
    if user:
        if user in ("system", "local service", "network service", "root") or user.endswith(
            "$"
        ):
            signals.append("builtin_system_principal")
        elif any(
            tok in user
            for tok in ("admin", "administrator", "svc-", "svc_", "service")
        ):
            signals.append("username_suggests_admin_or_service")
    cmdline = " ".join(
        [
            str(fields.get("command_line") or alert.get("command_line") or ""),
            str(
                fields.get("parent_command_line")
                or alert.get("parent_command_line")
                or ""
            ),
        ]
    ).lower()
    if cmdline and any(
        tok in cmdline
        for tok in (
            "gpupdate",
            "sccm",
            "intune",
            "ansible",
            "puppet",
            "wsus",
            "msiexec",
            "windowsdefender",
            "mpcmdrun",
        )
    ):
        signals.append("cmdline_suggests_admin_or_mgmt_tooling")
    return signals


def compute_pre_score_hints(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic risk hints for FACTS + UI chips (not a model score)."""
    fields = _resolve_process_fields(alert)
    path_raw = str(
        fields.get("process_path") or fields.get("file_path") or fields.get("process_name") or ""
    )
    path = _normalize_win_path(path_raw)
    basename = _basename(path_raw) or str(fields.get("process_name") or "").lower()
    cmdline = " ".join(
        [
            str(fields.get("command_line") or ""),
            str(fields.get("parent_command_line") or ""),
        ]
    ).lower()
    admin_signals = _admin_activity_signals(alert)

    # Markers use backslash form; path is normalized to forward slashes.
    temp_markers = tuple(m.replace("\\", "/") for m in _TEMP_OR_PROFILE_MARKERS)
    expected_markers = tuple(m.replace("\\", "/") for m in _EXPECTED_SYSTEM_PATH_MARKERS)

    path_temp = bool(path) and any(m in path for m in temp_markers)
    lolbin = basename in _LOLBIN_NAMES
    # Only judge "unexpected path" when we have a real directory component.
    has_dir = "/" in path
    expected_path = bool(path) and any(m in path for m in expected_markers)
    unexpected_lolbin = bool(lolbin and has_dir and not expected_path)
    encoded = bool(cmdline) and any(tok in cmdline for tok in _CMDLINE_RED_FLAGS)
    admin_user = bool(admin_signals)

    flags: List[str] = []
    if path_temp:
        flags.append("path_temp_or_userprofile")
    if unexpected_lolbin:
        flags.append("known_windows_binary_unexpected_path")
    if encoded:
        flags.append("encoded_powershell_or_cmdline_red_flags")
    if admin_user:
        flags.append("admin_user_signal")

    return {
        "path_temp_or_userprofile": path_temp,
        "known_windows_binary_unexpected_path": unexpected_lolbin,
        "encoded_powershell_or_cmdline_red_flags": encoded,
        "admin_user_signal": admin_user,
        "process_basename": basename or None,
        "flags": flags,
    }


def _ti_candidate_values(alert: Dict[str, Any], *, customer_safe: bool) -> List[str]:
    fields = _resolve_process_fields(alert)
    values: List[str] = []
    for key in ("hash_sha256", "hash_md5"):
        val = str(alert.get(key) or fields.get(key) or "").strip()
        if val:
            values.append(val)
    host = str(
        alert.get("hostname")
        or alert.get("asset_hostname")
        or alert.get("destination_host")
        or ""
    ).strip()
    if host:
        values.append(host)
    if not customer_safe:
        for key in ("source_ip", "destination_ip", "asset_ip"):
            val = str(alert.get(key) or "").strip()
            if val:
                values.append(val)
    # Dedupe preserving order
    seen = set()
    out: List[str] = []
    for v in values:
        low = v.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(v)
    return out


def _load_ti_hits(
    tenant_id: str, alert: Dict[str, Any], *, customer_safe: bool
) -> List[Dict[str, Any]]:
    candidates = _ti_candidate_values(alert, customer_safe=customer_safe)
    if not tenant_id or not candidates:
        return []
    try:
        rows = fetch_all(
            """
            SELECT ioc_type, ioc_value, reputation_status, confidence_score, summary
            FROM tenant_threat_intel_iocs
            WHERE tenant_id = %s::uuid
              AND status = 'active'
              AND ioc_value = ANY(%s)
            ORDER BY
              CASE reputation_status
                WHEN 'MALICIOUS' THEN 0
                WHEN 'SUSPICIOUS' THEN 1
                ELSE 2
              END,
              confidence_score DESC NULLS LAST
            LIMIT %s;
            """,
            (tenant_id, candidates, ENRICHMENT_LIST_LIMIT),
        )
    except Exception:  # noqa: BLE001
        logger.exception("TI enrichment lookup failed")
        return []
    hits: List[Dict[str, Any]] = []
    for row in rows or []:
        item = {
            "ioc_type": row.get("ioc_type"),
            "reputation_status": row.get("reputation_status"),
            "confidence_score": row.get("confidence_score"),
        }
        if customer_safe:
            # Expose value only for hashes/domains — not raw IPs.
            ioc_type = str(row.get("ioc_type") or "").upper()
            if ioc_type in ("FILE_HASH", "DOMAIN", "URL"):
                item["ioc_value"] = row.get("ioc_value")
            else:
                item["ioc_value"] = "[redacted]"
            item["summary"] = (str(row.get("summary") or "")[:240] or None)
        else:
            item["ioc_value"] = row.get("ioc_value")
            item["summary"] = (str(row.get("summary") or "")[:400] or None)
        hits.append(item)
    return hits


def _load_related_alerts(
    tenant_id: str,
    alert: Dict[str, Any],
    *,
    customer_safe: bool,
) -> Dict[str, Any]:
    alert_id = str(alert.get("id") or alert.get("alert_id") or "").strip()
    host = str(
        alert.get("hostname")
        or alert.get("asset_hostname")
        or alert.get("destination_host")
        or ""
    ).strip()
    event_time = _parse_event_time(alert)
    empty = {
        "window_seconds": RELATED_WINDOW_SECONDS,
        "count": 0,
        "items": [],
    }
    if not tenant_id or not host or not event_time or not alert_id:
        return empty
    try:
        rows = fetch_all(
            """
            SELECT
              id::text,
              alert_title,
              severity,
              status,
              event_time::text,
              EXTRACT(EPOCH FROM (event_time - %s::timestamptz))::int AS offset_seconds
            FROM security_alerts
            WHERE tenant_id = %s::uuid
              AND id <> %s::uuid
              AND destination_host = %s
              AND event_time BETWEEN
                %s::timestamptz - (%s::text || ' seconds')::interval
                AND %s::timestamptz + (%s::text || ' seconds')::interval
            ORDER BY event_time ASC
            LIMIT %s;
            """,
            (
                event_time.isoformat(),
                tenant_id,
                alert_id,
                host,
                event_time.isoformat(),
                RELATED_WINDOW_SECONDS,
                event_time.isoformat(),
                RELATED_WINDOW_SECONDS,
                ENRICHMENT_LIST_LIMIT,
            ),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Related-alert enrichment failed")
        return empty
    items: List[Dict[str, Any]] = []
    for row in rows or []:
        item: Dict[str, Any] = {
            "alert_title": row.get("alert_title"),
            "severity": row.get("severity"),
            "status": row.get("status"),
            "offset_seconds": row.get("offset_seconds"),
        }
        if not customer_safe:
            item["id"] = row.get("id")
            item["event_time"] = row.get("event_time")
        items.append(item)
    return {
        "window_seconds": RELATED_WINDOW_SECONDS,
        "count": len(items),
        "items": items,
    }


def _fp_item_from_row(row: Dict[str, Any], *, customer_safe: bool) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "alert_title": row.get("alert_title"),
        "status": row.get("status"),
        "event_time": row.get("event_time"),
    }
    if not customer_safe:
        item["id"] = row.get("id")
        item["destination_host"] = row.get("destination_host")
        if row.get("rule_id"):
            item["rule_id"] = row.get("rule_id")
    return item


def _load_prior_fp_and_suppressions(
    tenant_id: str,
    alert: Dict[str, Any],
    *,
    customer_safe: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Prior FP pattern memory:
      - same host + title (Phase 1)
      - same rule_id across tenant (and optional global for admin)
      - same rule_id + similar process path/name
    Also strengthens active suppression hits for FACTS.
    """
    alert_id = str(alert.get("id") or alert.get("alert_id") or "").strip()
    nil_uuid = "00000000-0000-0000-0000-000000000000"
    exclude_id = alert_id or nil_uuid
    host = str(
        alert.get("hostname")
        or alert.get("asset_hostname")
        or alert.get("destination_host")
        or ""
    ).strip()
    title = str(alert.get("alert_title") or alert.get("title") or "").strip()
    fields = _resolve_process_fields(alert)
    rule_id = str(alert.get("wazuh_rule_id") or fields.get("wazuh_rule_id") or "").strip()
    process_path = str(
        fields.get("process_path")
        or alert.get("process_name")
        or alert.get("file_path")
        or ""
    ).strip()
    process_base = _basename(process_path) or str(fields.get("process_name") or "").strip().lower()

    fp: Dict[str, Any] = {
        "count": 0,
        "match_basis": [],
        "items": [],
        "by_basis": {
            "host_title": {"count": 0, "items": []},
            "same_rule": {"count": 0, "items": []},
            "same_process": {"count": 0, "items": []},
            "global_same_rule": {"count": 0},
        },
    }
    suppressions: Dict[str, Any] = {
        "count": 0,
        "match": False,
        "items": [],
    }

    if not tenant_id:
        return fp, suppressions

    match_basis: List[str] = []
    all_items: List[Dict[str, Any]] = []
    seen_ids: set = set()

    def _absorb(rows: Optional[List[Dict[str, Any]]], basis: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for row in rows or []:
            item = _fp_item_from_row(row, customer_safe=customer_safe)
            item["match_basis"] = basis
            items.append(item)
            rid = str(row.get("id") or "")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                all_items.append(item)
        return items

    try:
        # 1) Same host + title
        host_title_rows: List[Dict[str, Any]] = []
        if host and title:
            host_title_rows = fetch_all(
                """
                SELECT
                  id::text,
                  alert_title,
                  destination_host,
                  status,
                  event_time::text,
                  raw_event->'rule'->>'id' AS rule_id
                FROM security_alerts
                WHERE tenant_id = %s::uuid
                  AND status = 'false_positive'
                  AND id <> %s::uuid
                  AND destination_host = %s
                  AND alert_title = %s
                ORDER BY event_time DESC NULLS LAST
                LIMIT %s;
                """,
                (tenant_id, exclude_id, host, title, ENRICHMENT_LIST_LIMIT),
            ) or []
            if host_title_rows:
                match_basis.append("host+title")
        ht_items = _absorb(host_title_rows, "host+title")
        fp["by_basis"]["host_title"] = {
            "count": len(ht_items),
            "items": ht_items,
        }

        # 2) Same rule_id across tenant (count + sample)
        same_rule_count = 0
        same_rule_rows: List[Dict[str, Any]] = []
        if rule_id:
            count_row = fetch_one(
                """
                SELECT COUNT(*)::int AS cnt
                FROM security_alerts
                WHERE tenant_id = %s::uuid
                  AND status = 'false_positive'
                  AND id <> %s::uuid
                  AND raw_event->'rule'->>'id' = %s;
                """,
                (tenant_id, exclude_id, rule_id),
            )
            same_rule_count = int((count_row or {}).get("cnt") or 0)
            if same_rule_count:
                match_basis.append("same_rule")
                same_rule_rows = fetch_all(
                    """
                    SELECT
                      id::text,
                      alert_title,
                      destination_host,
                      status,
                      event_time::text,
                      raw_event->'rule'->>'id' AS rule_id
                    FROM security_alerts
                    WHERE tenant_id = %s::uuid
                      AND status = 'false_positive'
                      AND id <> %s::uuid
                      AND raw_event->'rule'->>'id' = %s
                    ORDER BY event_time DESC NULLS LAST
                    LIMIT %s;
                    """,
                    (tenant_id, exclude_id, rule_id, ENRICHMENT_LIST_LIMIT),
                ) or []
        sr_items = _absorb(same_rule_rows, "same_rule")
        fp["by_basis"]["same_rule"] = {
            "count": same_rule_count,
            "items": sr_items,
        }

        # 3) Same rule + similar process path/name (message / title / Image)
        same_proc_count = 0
        same_proc_rows: List[Dict[str, Any]] = []
        if rule_id and process_base and len(process_base) >= 3:
            like = f"%{process_base}%"
            count_row = fetch_one(
                """
                SELECT COUNT(*)::int AS cnt
                FROM security_alerts
                WHERE tenant_id = %s::uuid
                  AND status = 'false_positive'
                  AND id <> %s::uuid
                  AND raw_event->'rule'->>'id' = %s
                  AND (
                    lower(COALESCE(alert_title, '')) LIKE %s
                    OR lower(COALESCE(raw_event#>>'{data,win,system,message}', '')) LIKE %s
                    OR lower(COALESCE(raw_event#>>'{data,win,eventdata,Image}', '')) LIKE %s
                    OR lower(COALESCE(raw_event#>>'{data,process_name}', '')) LIKE %s
                    OR lower(COALESCE(raw_event#>>'{syscheck,path}', '')) LIKE %s
                  );
                """,
                (tenant_id, exclude_id, rule_id, like, like, like, like, like),
            )
            same_proc_count = int((count_row or {}).get("cnt") or 0)
            if same_proc_count:
                match_basis.append("same_process")
                same_proc_rows = fetch_all(
                    """
                    SELECT
                      id::text,
                      alert_title,
                      destination_host,
                      status,
                      event_time::text,
                      raw_event->'rule'->>'id' AS rule_id
                    FROM security_alerts
                    WHERE tenant_id = %s::uuid
                      AND status = 'false_positive'
                      AND id <> %s::uuid
                      AND raw_event->'rule'->>'id' = %s
                      AND (
                        lower(COALESCE(alert_title, '')) LIKE %s
                        OR lower(COALESCE(raw_event#>>'{data,win,system,message}', '')) LIKE %s
                        OR lower(COALESCE(raw_event#>>'{data,win,eventdata,Image}', '')) LIKE %s
                        OR lower(COALESCE(raw_event#>>'{data,process_name}', '')) LIKE %s
                        OR lower(COALESCE(raw_event#>>'{syscheck,path}', '')) LIKE %s
                      )
                    ORDER BY event_time DESC NULLS LAST
                    LIMIT %s;
                    """,
                    (
                        tenant_id,
                        exclude_id,
                        rule_id,
                        like,
                        like,
                        like,
                        like,
                        like,
                        ENRICHMENT_LIST_LIMIT,
                    ),
                ) or []
        sp_items = _absorb(same_proc_rows, "same_process")
        fp["by_basis"]["same_process"] = {
            "count": same_proc_count,
            "items": sp_items,
            "process_basename": process_base or None,
        }

        # 4) Admin-only: global same-rule FP pressure (other tenants)
        global_same_rule = 0
        if rule_id and not customer_safe:
            grow = fetch_one(
                """
                SELECT COUNT(*)::int AS cnt
                FROM security_alerts
                WHERE status = 'false_positive'
                  AND tenant_id <> %s::uuid
                  AND raw_event->'rule'->>'id' = %s;
                """,
                (tenant_id, rule_id),
            )
            global_same_rule = int((grow or {}).get("cnt") or 0)
            if global_same_rule:
                match_basis.append("global_same_rule")
        fp["by_basis"]["global_same_rule"] = {"count": global_same_rule}

        fp = {
            "count": len(all_items) if all_items else max(
                len(ht_items), same_rule_count, same_proc_count
            ),
            "match_basis": match_basis,
            "items": all_items[:ENRICHMENT_LIST_LIMIT],
            "by_basis": fp["by_basis"],
            "prior_fp_same_rule": same_rule_count,
            "prior_fp_same_process": same_proc_count,
            "prior_fp_host_title": len(ht_items),
            "prior_fp_global_same_rule": global_same_rule,
        }
    except Exception:  # noqa: BLE001
        logger.exception("Prior FP enrichment failed")

    if rule_id:
        try:
            sup_rows = fetch_all(
                """
                SELECT
                  rule_id,
                  scope,
                  hostname,
                  process_path_value,
                  match_process_path,
                  reason,
                  created_at::text
                FROM alert_suppressions
                WHERE disabled_at IS NULL
                  AND (expires_at IS NULL OR expires_at > now())
                  AND rule_id = %s
                  AND (
                    scope = 'global'
                    OR (scope = 'tenant' AND tenant_id = %s::uuid)
                    OR (
                      scope = 'host'
                      AND tenant_id = %s::uuid
                      AND (%s = '' OR hostname = %s OR hostname_value = %s)
                    )
                  )
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (
                    rule_id,
                    tenant_id,
                    tenant_id,
                    host,
                    host,
                    host,
                    ENRICHMENT_LIST_LIMIT,
                ),
            )
            s_items: List[Dict[str, Any]] = []
            for row in sup_rows or []:
                proc_val = str(row.get("process_path_value") or "").strip().lower()
                process_path_matched = False
                if proc_val and process_base:
                    process_path_matched = (
                        process_base in proc_val
                        or proc_val in process_path.lower()
                        or _basename(proc_val) == process_base
                    )
                elif proc_val and process_path:
                    process_path_matched = proc_val in process_path.lower()

                item: Dict[str, Any] = {
                    "rule_id": row.get("rule_id"),
                    "scope": row.get("scope"),
                    "reason": (str(row.get("reason") or "")[:240] or None),
                    "suppression_match": True,
                    "process_path_matched": process_path_matched
                    or bool(row.get("match_process_path") is False and not proc_val),
                }
                # Rule-level active suppression always counts as a match.
                item["process_path_matched"] = bool(process_path_matched)
                if not customer_safe:
                    item["hostname"] = row.get("hostname")
                    item["process_path_value"] = row.get("process_path_value")
                    item["created_at"] = row.get("created_at")
                    item["match_process_path"] = row.get("match_process_path")
                s_items.append(item)
            suppressions = {
                "count": len(s_items),
                "match": bool(s_items),
                "items": s_items,
            }
        except Exception:  # noqa: BLE001
            logger.exception("Suppression enrichment failed")

    return fp, suppressions


def _hash_reputation_label(ti_hits: List[Dict[str, Any]], alert: Dict[str, Any]) -> str:
    fields = _resolve_process_fields(alert)
    hashes = {
        str(alert.get("hash_sha256") or fields.get("hash_sha256") or "").strip().lower(),
        str(alert.get("hash_md5") or fields.get("hash_md5") or "").strip().lower(),
    }
    hashes.discard("")
    if not hashes:
        return "no_hash"
    for hit in ti_hits:
        if str(hit.get("ioc_type") or "").upper() != "FILE_HASH":
            continue
        val = str(hit.get("ioc_value") or "").strip().lower()
        if val in hashes or hit.get("ioc_value") == "[redacted]":
            return str(hit.get("reputation_status") or "matched").lower()
    return "none"


def _vt_api_key() -> Optional[str]:
    """
    Server-side only. Prefer VT_API_KEY / VT_API_KEY_FILE (via read_secret),
    then VIRUSTOTAL_* aliases. Never expose to browser clients.
    """
    file_override = (os.getenv("VT_API_KEY_FILE") or "").strip() or None
    paths = [
        p
        for p in (
            file_override,
            "/run/secrets/vt_api_key",
            "/opt/mssp-control/.secrets/vt_api_key",
        )
        if p
    ]
    return read_secret("VT_API_KEY", *paths) or read_secret(
        "VIRUSTOTAL_API_KEY",
        "/run/secrets/virustotal_api_key",
        "/opt/mssp-control/.secrets/virustotal_api_key",
    )


def _lookup_virustotal_hash(file_hash: str) -> Dict[str, Any]:
    """
    Gated VirusTotal v3 file hash lookup (SHA256/MD5).
    GET https://www.virustotal.com/api/v3/files/{hash}
    Timeout ~2s; soft-fail on missing key, rate-limit, or errors.
    Returns last_analysis_stats: malicious, suspicious, harmless, undetected.
    """
    key = _vt_api_key()
    if not key:
        logger.info("VT lookup skipped (No API Key configured)")
        return {"status": "not_configured", "message": "No API Key configured"}
    digest = str(file_hash or "").strip().lower()
    if not digest or len(digest) not in (32, 64) or not all(
        c in "0123456789abcdef" for c in digest
    ):
        return {"status": "no_hash"}
    url = f"https://www.virustotal.com/api/v3/files/{digest}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "x-apikey": key,
            "Accept": "application/json",
            "User-Agent": "mssp-control-tier1-triage/3",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=VT_TIMEOUT_SECONDS) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        stats = (
            ((raw.get("data") or {}).get("attributes") or {}).get("last_analysis_stats")
            or {}
        )
        return {
            "status": "ok",
            "hash": digest,
            "malicious": int(stats.get("malicious") or 0),
            "suspicious": int(stats.get("suspicious") or 0),
            "harmless": int(stats.get("harmless") or 0),
            "undetected": int(stats.get("undetected") or 0),
        }
    except TimeoutError:
        logger.info("VT lookup skipped (timeout after %.1fs)", VT_TIMEOUT_SECONDS)
        return {"status": "timeout", "hash": digest, "message": "timeout"}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"status": "not_found", "hash": digest}
        if exc.code == 429:
            logger.info("VT lookup skipped (rate limited)")
            return {
                "status": "rate_limited",
                "hash": digest,
                "http_status": 429,
                "message": "rate limited",
            }
        logger.info("VT lookup soft-failed (HTTP %s)", exc.code)
        return {
            "status": "error",
            "hash": digest,
            "http_status": exc.code,
            "message": f"HTTP {exc.code}",
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("VT lookup soft-failed: %s", type(exc).__name__)
        return {
            "status": "error",
            "hash": digest,
            "message": type(exc).__name__,
        }


def _auto_close_enabled() -> bool:
    """OPT-IN only. Default false — no silent auto-close when unset."""
    return (os.getenv("ENABLE_AUTO_CLOSE_LOW_RISK") or "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _wazuh_rule_level(alert: Dict[str, Any]) -> Optional[int]:
    """Best-effort Wazuh rule level from enriched fields or raw_event."""
    for key in ("wazuh_rule_level", "rule_level", "level"):
        raw = alert.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    raw_event = alert.get("raw_event")
    if isinstance(raw_event, str):
        try:
            raw_event = json.loads(raw_event)
        except (TypeError, ValueError):
            raw_event = None
    if isinstance(raw_event, dict):
        rule = raw_event.get("rule") if isinstance(raw_event.get("rule"), dict) else {}
        for candidate in (
            rule.get("level"),
            raw_event.get("level"),
            (raw_event.get("data") or {}).get("level")
            if isinstance(raw_event.get("data"), dict)
            else None,
        ):
            if candidate is None:
                continue
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
    return None


def _severity_allows_auto_close(alert: Dict[str, Any]) -> bool:
    """
    Hard guard: NEVER auto-close medium/high/critical or Wazuh level 6+.
    Allowed only when severity is low OR (when severity absent) level <= 5.
    Fail closed when neither low severity nor a safe level can be verified.
    """
    sev = str(alert.get("severity") or "").strip().lower()
    if sev in ("medium", "high", "critical", "urgent"):
        return False
    level = _wazuh_rule_level(alert)
    if level is not None and level >= 6:
        return False
    if sev == "low":
        return True
    if level is not None and level <= 5:
        return True
    return False


def _matches_known_fp_pattern(enrichment: Dict[str, Any]) -> bool:
    """
    Known false-positive pattern for guarded auto-close (opt-in only).

    Accept when ANY of:
      1. Signature is explicitly signed, OR path is a likely_signed system path
         (Windows System32/SysWOW64 or common Unix bin dirs — see _SIGNED_PATH_HINTS).
      2. Verified internal admin/script signal from enrichment:
         pre_score_hints.admin_user_signal OR admin_activity_signals
         (builtin_system_principal / username_suggests_admin_or_service /
         cmdline_suggests_admin_or_mgmt_tooling), AND no high-risk path/cmdline
         pre_score flags (temp/userprofile, unexpected LOLBin path, encoded PS).

    High-risk path/cmdline always disqualifies.
    """
    hints = enrichment.get("pre_score_hints") or {}
    high_risk = bool(
        hints.get("path_temp_or_userprofile")
        or hints.get("known_windows_binary_unexpected_path")
        or hints.get("encoded_powershell_or_cmdline_red_flags")
    )
    if high_risk:
        return False

    sig = enrichment.get("signature") or {}
    sig_status = str(sig.get("status") or "").strip().lower()
    if sig_status in ("signed", "likely_signed_path"):
        return True

    admin_signals = list(
        (enrichment.get("user_context") or {}).get("admin_activity_signals") or []
    )
    admin_ok = bool(hints.get("admin_user_signal")) or any(
        s
        in (
            "builtin_system_principal",
            "username_suggests_admin_or_service",
            "cmdline_suggests_admin_or_mgmt_tooling",
        )
        for s in admin_signals
    )
    return admin_ok


def compute_ai_queue(verdict: str, confidence: float) -> Optional[str]:
    """Low-priority queue when BENIGN_FALSE_POSITIVE and confidence >= 85."""
    if (
        str(verdict or "").strip().upper() == "BENIGN_FALSE_POSITIVE"
        and float(confidence) >= LOW_PRIORITY_CONFIDENCE_MIN
    ):
        return "low_priority"
    return None


def _persist_alert_ai_fields(
    *,
    alert_id: str,
    verdict: str,
    confidence: float,
    ai_queue: Optional[str],
) -> None:
    """Write Tier-1 fields onto security_alerts for fast list filters."""
    fetch_one_write(
        """
        UPDATE security_alerts
        SET ai_verdict = %s,
            ai_confidence = %s,
            ai_queue = %s,
            ai_triaged_at = now(),
            updated_at = now()
        WHERE id = %s::uuid
        RETURNING id::text;
        """,
        (verdict, confidence, ai_queue, alert_id),
    )


def _try_auto_close_low_risk(
    *,
    alert_id: str,
    tenant_id: str,
    alert: Dict[str, Any],
    enrichment: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    OPT-IN auto-resolve. Default ENABLE_AUTO_CLOSE_LOW_RISK=false → no-op.
    Requires ALL of: low severity/level guard, confidence >= 95,
    BENIGN_FALSE_POSITIVE, known FP pattern. Uses status=closed (existing enum)
    plus ai_auto_closed / ai_resolution_label — never invents new status values.
    """
    if not _auto_close_enabled():
        return {"auto_closed": False, "reason": "flag_disabled"}

    verdict = str(result.get("verdict") or "")
    try:
        confidence = float(result.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    if verdict != "BENIGN_FALSE_POSITIVE":
        return {"auto_closed": False, "reason": "verdict_not_benign"}
    if confidence < AUTO_CLOSE_CONFIDENCE_MIN:
        return {"auto_closed": False, "reason": "confidence_below_95"}
    if not _severity_allows_auto_close(alert):
        return {"auto_closed": False, "reason": "severity_or_level_blocked"}
    if not _matches_known_fp_pattern(enrichment):
        return {"auto_closed": False, "reason": "no_known_fp_pattern"}

    # Skip if already terminal.
    current = str(alert.get("status") or "").strip().lower()
    if current in ("closed", "false_positive"):
        return {"auto_closed": False, "reason": "already_terminal"}

    label = AI_RESOLUTION_AUTO_CLOSE
    note = (
        f"{label}: verdict={verdict} confidence={confidence:.1f} "
        f"severity={alert.get('severity')} wazuh_level={_wazuh_rule_level(alert)}"
    )[:4000]
    row = fetch_one_write(
        """
        UPDATE security_alerts
        SET status = 'closed',
            customer_visible = false,
            ai_auto_closed = true,
            ai_resolution_label = %s,
            ai_queue = 'low_priority',
            ai_technical_summary = CASE
              WHEN ai_technical_summary IS NULL OR btrim(ai_technical_summary) = ''
              THEN %s
              ELSE left(ai_technical_summary || E'\\n' || %s, 4000)
            END,
            updated_at = now()
        WHERE id = %s::uuid
          AND status NOT IN ('closed', 'false_positive')
        RETURNING id::text, status;
        """,
        (label, note, note, alert_id),
    )
    if not row:
        return {"auto_closed": False, "reason": "update_skipped"}

    try:
        from app.services.audit_service import write_audit_event

        write_audit_event(
            action="alerts.ai_auto_close",
            entity_type="security_alert",
            entity_id=alert_id,
            tenant_id=tenant_id,
            actor_email="system:ai_tier1_triage",
            actor_role="system",
            details={
                "resolution": label,
                "verdict": verdict,
                "confidence": confidence,
                "severity": alert.get("severity"),
                "wazuh_rule_level": _wazuh_rule_level(alert),
                "signature_status": (enrichment.get("signature") or {}).get("status"),
                "pre_score_flags": list(
                    (enrichment.get("pre_score_hints") or {}).get("flags") or []
                ),
                "summary": str(result.get("summary") or "")[:500],
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("audit for AI auto-close failed alert_id=%s", alert_id)

    logger.info(
        "AI auto-closed alert %s (confidence=%.1f) — ENABLE_AUTO_CLOSE_LOW_RISK",
        alert_id,
        confidence,
    )
    return {
        "auto_closed": True,
        "status": "closed",
        "ai_resolution_label": label,
        "reason": "ok",
    }


def _compute_action_guardrails(
    *,
    ti_hit: bool,
    prior_fp: Dict[str, Any],
    suppressions: Dict[str, Any],
    pre_score_hints: Dict[str, Any],
    vt: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Deterministic recommendation bias + soft queue suggestion.
    Never auto-executes; human confirm only.
    """
    same_rule = int(prior_fp.get("prior_fp_same_rule") or 0)
    same_proc = int(prior_fp.get("prior_fp_same_process") or 0)
    host_title = int(prior_fp.get("prior_fp_host_title") or 0)
    global_rule = int(prior_fp.get("prior_fp_global_same_rule") or 0)
    suppression_match = bool(suppressions.get("match"))
    high_risk_path = bool(
        pre_score_hints.get("path_temp_or_userprofile")
        or pre_score_hints.get("known_windows_binary_unexpected_path")
        or pre_score_hints.get("encoded_powershell_or_cmdline_red_flags")
    )
    vt_mal = int(vt.get("malicious") or 0) if vt.get("status") == "ok" else 0
    vt_sus = int(vt.get("suspicious") or 0) if vt.get("status") == "ok" else 0
    external_bad = vt_mal > 0 or vt_sus >= 3

    strong_fp = (
        (same_rule >= 3 or same_proc >= 2 or host_title >= 2 or global_rule >= 10)
        and suppression_match
        and not ti_hit
        and not high_risk_path
        and not external_bad
    )
    medium_fp = (same_rule >= 1 or same_proc >= 1 or host_title >= 1) and not ti_hit

    if strong_fp:
        pressure = "high"
        prefer = "AUTO_SUPPRESS"
        rationale = (
            "Strong prior false-positive / suppression pattern for this rule "
            "(and process where available) with no TI hit and no high-risk "
            "path/cmdline hints — bias toward human-confirmed suppression."
        )
        queue: Optional[str] = "low_priority"
    elif ti_hit or high_risk_path or external_bad:
        pressure = "low"
        prefer = "ISOLATE_AGENT" if (ti_hit or external_bad) else "INVESTIGATE_HOST"
        bits = []
        if ti_hit:
            bits.append("internal TI hit")
        if high_risk_path:
            bits.append("suspicious path/cmdline heuristics")
        if external_bad:
            bits.append("VirusTotal detections")
        rationale = (
            "Elevated risk signals ("
            + ", ".join(bits)
            + ") — bias away from AUTO_SUPPRESS toward investigation/isolation "
            "(human confirm only)."
        )
        queue = None
    elif medium_fp and suppression_match:
        pressure = "medium"
        prefer = "AUTO_SUPPRESS"
        rationale = (
            "Some prior FP history and an active suppression match — consider "
            "human-confirmed suppression after quick review."
        )
        queue = "low_priority"
    elif medium_fp:
        pressure = "medium"
        prefer = "INVESTIGATE_HOST"
        rationale = (
            "Some prior FP history without a strong suppression match — "
            "investigate before suppressing."
        )
        queue = None
    else:
        pressure = "low"
        prefer = "INVESTIGATE_HOST"
        rationale = (
            "No strong FP/suppression pattern — default to host investigation."
        )
        queue = None

    return {
        "historical_fp_pressure": pressure,
        "prefer_recommended_action": prefer,
        "action_rationale": rationale,
        "queue_suggestion": queue,
        "never_auto_execute": True,
    }


def enrich_alert_context(
    alert: Dict[str, Any],
    *,
    customer_safe: bool = False,
) -> Dict[str, Any]:
    """
    Live DB enrichment for Tier-1 triage. Fast bounded queries only.
    External VirusTotal is optional/gated; absent key → not_configured.
    """
    tenant_id = str(alert.get("tenant_id") or "").strip()
    hostname = str(
        alert.get("hostname")
        or alert.get("asset_hostname")
        or alert.get("destination_host")
        or ""
    ).strip() or None
    device_type = str(alert.get("device_type") or "").strip() or "unknown"
    signature = _extract_signature_status(alert)
    admin_signals = _admin_activity_signals(alert)
    pre_score_hints = compute_pre_score_hints(alert)
    ti_hits = _load_ti_hits(tenant_id, alert, customer_safe=customer_safe)
    related = _load_related_alerts(tenant_id, alert, customer_safe=customer_safe)
    prior_fp, suppressions = _load_prior_fp_and_suppressions(
        tenant_id, alert, customer_safe=customer_safe
    )
    hash_rep = _hash_reputation_label(ti_hits, alert)

    fields = _resolve_process_fields(alert)
    file_hash = str(fields.get("hash_sha256") or fields.get("hash_md5") or "").strip()
    # Always a dict so clients can read .status without special-casing strings.
    if not _vt_api_key():
        logger.info("VT lookup skipped (No API Key configured)")
        external_vt: Dict[str, Any] = {
            "status": "not_configured",
            "message": "No API Key configured",
        }
    elif not file_hash:
        external_vt = {"status": "no_hash"}
    else:
        external_vt = _lookup_virustotal_hash(file_hash)
    vt_obj = external_vt

    guardrails = _compute_action_guardrails(
        ti_hit=bool(ti_hits),
        prior_fp=prior_fp,
        suppressions=suppressions,
        pre_score_hints=pre_score_hints,
        vt=vt_obj,
    )

    asset: Dict[str, Any] = {
        "hostname": hostname,
        "device_type": device_type,
        "asset_category": alert.get("asset_category"),
        "asset_type": alert.get("asset_type"),
        "os_name": alert.get("asset_os_name") or alert.get("operating_system"),
        "criticality": alert.get("asset_criticality") or alert.get("criticality"),
    }
    if not customer_safe:
        asset["owner"] = alert.get("asset_owner")
        asset["ip"] = alert.get("asset_ip")

    user_context: Dict[str, Any] = {
        "admin_activity_signals": admin_signals,
    }
    if not customer_safe:
        user_context["source_user"] = fields.get("source_user") or alert.get(
            "source_user"
        )

    enrichment: Dict[str, Any] = {
        "asset": {k: v for k, v in asset.items() if v not in (None, "", [])},
        "user_context": user_context,
        "signature": signature,
        "pre_score_hints": pre_score_hints,
        "threat_intel": {
            "hit": bool(ti_hits),
            "match_count": len(ti_hits),
            "matches": ti_hits,
            "hash_reputation": hash_rep,
            "external_vt": external_vt,
        },
        "related_alerts": related,
        "prior_false_positives": prior_fp,
        "active_suppressions": suppressions,
        "action_guardrails": guardrails,
        "context_summary": {
            "device_type": device_type,
            "ti_hit": bool(ti_hits),
            "related_alerts_count": int(related.get("count") or 0),
            "prior_fp_count": int(prior_fp.get("count") or 0),
            "prior_fp_same_rule": int(prior_fp.get("prior_fp_same_rule") or 0),
            "prior_fp_same_process": int(prior_fp.get("prior_fp_same_process") or 0),
            "suppression_match": bool(suppressions.get("match")),
            "active_suppression_count": int(suppressions.get("count") or 0),
            "signature_status": signature.get("status") or "unknown",
            "hash_reputation": hash_rep,
            "admin_activity_signal_count": len(admin_signals),
            "historical_fp_pressure": guardrails.get("historical_fp_pressure"),
            "pre_score_flags": list(pre_score_hints.get("flags") or []),
            "queue_suggestion": guardrails.get("queue_suggestion"),
            "vt_status": vt_obj.get("status"),
            "vt_malicious": vt_obj.get("malicious") if vt_obj.get("status") == "ok" else None,
            "vt_suspicious": vt_obj.get("suspicious") if vt_obj.get("status") == "ok" else None,
            "vt_harmless": vt_obj.get("harmless") if vt_obj.get("status") == "ok" else None,
            "vt_undetected": vt_obj.get("undetected") if vt_obj.get("status") == "ok" else None,
        },
    }
    return enrichment


def build_user_prompt(payload: Dict[str, Any], enrichment: Optional[Dict[str, Any]] = None) -> str:
    facts_for_model: Dict[str, Any] = {}
    if enrichment:
        # Compact FACTS — avoid dumping full item lists into the model context.
        summary = enrichment.get("context_summary") or {}
        prior = enrichment.get("prior_false_positives") or {}
        facts_for_model = {
            "asset": enrichment.get("asset") or {},
            "user_context": enrichment.get("user_context") or {},
            "signature": enrichment.get("signature") or {},
            "pre_score_hints": enrichment.get("pre_score_hints") or {},
            "threat_intel": {
                "hit": (enrichment.get("threat_intel") or {}).get("hit"),
                "match_count": (enrichment.get("threat_intel") or {}).get("match_count"),
                "hash_reputation": (enrichment.get("threat_intel") or {}).get(
                    "hash_reputation"
                ),
                "external_vt": (enrichment.get("threat_intel") or {}).get("external_vt"),
                "matches": (enrichment.get("threat_intel") or {}).get("matches") or [],
            },
            "related_alerts_in_window": {
                "window_seconds": (enrichment.get("related_alerts") or {}).get(
                    "window_seconds"
                ),
                "count": summary.get("related_alerts_count"),
                "items": (enrichment.get("related_alerts") or {}).get("items") or [],
            },
            "prior_false_positives": {
                "count": summary.get("prior_fp_count"),
                "prior_fp_same_rule": prior.get("prior_fp_same_rule"),
                "prior_fp_same_process": prior.get("prior_fp_same_process"),
                "prior_fp_host_title": prior.get("prior_fp_host_title"),
                "prior_fp_global_same_rule": prior.get("prior_fp_global_same_rule"),
                "match_basis": prior.get("match_basis"),
                "items": prior.get("items") or [],
            },
            "active_suppressions": {
                "count": summary.get("active_suppression_count"),
                "suppression_match": summary.get("suppression_match"),
                "items": (enrichment.get("active_suppressions") or {}).get("items")
                or [],
            },
            "action_guardrails": enrichment.get("action_guardrails") or {},
            "context_summary": summary,
        }
    lines = [
        "Analyze this telemetry alert and return structured triage JSON only.",
        "Evaluate Process Name, Path, Parent Process, CommandLine, and User together.",
        "Base conclusions on Telemetry + FACTS only. Unknown means unknown.",
        "Honor action_guardrails biases but never claim silent auto-close/suppress/isolate.",
        "",
        "Telemetry:",
        _redact(json.dumps(payload, default=str, indent=2), 2800),
        "",
        "FACTS (retrieved from platform — do not invent missing fields):",
        _redact(json.dumps(facts_for_model, default=str, indent=2), 3200)
        if facts_for_model
        else "(none)",
    ]
    return "\n".join(lines)


def _normalize_result(parsed: Dict[str, Any], fallback_rule: str = "") -> Dict[str, Any]:
    verdict = str(parsed.get("verdict") or "").strip().upper()
    if verdict not in VERDICTS:
        verdict = "SUSPICIOUS"
    try:
        confidence = float(parsed.get("confidence"))
    except (TypeError, ValueError):
        confidence = 50.0
    confidence = max(0.0, min(100.0, confidence))
    action = str(parsed.get("recommended_action") or "").strip().upper()
    if action not in ACTIONS:
        action = "INVESTIGATE_HOST"
    summary = str(parsed.get("summary") or "").strip()[:2000]
    if not summary:
        summary = "AI triage completed without a detailed summary."
    scope_raw = parsed.get("suggested_suppression_scope") or {}
    if not isinstance(scope_raw, dict):
        scope_raw = {}
    scope = {
        "rule_id": str(scope_raw.get("rule_id") or fallback_rule or "")[:512],
        "process_path": str(scope_raw.get("process_path") or "")[:1024],
        "justification": str(scope_raw.get("justification") or summary)[:2000],
    }
    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary,
        "recommended_action": action,
        "suggested_suppression_scope": scope,
    }


def _call_ollama_chat(
    user_prompt: str, *, alert_id: str = "", cache_status: str = "miss"
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    import time

    root = _ollama_root()
    model = (os.getenv("AI_ALERT_MODEL") or "qwen2.5:7b").strip()
    timeout = _timeout_seconds()
    url = f"{root}/api/chat"
    num_thread = _num_thread()
    num_predict = _num_predict()
    num_ctx = _num_ctx()
    logger.info(
        "AI triage Ollama request start alert_id=%s cache=%s model=%s "
        "num_thread=%s num_ctx=%s num_predict=%s",
        alert_id or "n/a",
        cache_status,
        model,
        num_thread,
        num_ctx,
        num_predict,
    )
    started = time.monotonic()
    body = {
        "model": model,
        "stream": False,
        "format": JSON_SCHEMA,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "num_thread": num_thread,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "temperature": 0.1,
        },
        "keep_alive": _keep_alive(),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise TimeoutError(
            f"Ollama triage timed out after {timeout:.0f}s"
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError) or "timed out" in str(exc).lower():
            raise TimeoutError(
                f"Ollama triage timed out after {timeout:.0f}s"
            ) from exc
        raise RuntimeError(f"Ollama unreachable: {exc}") from exc

    content = ((raw.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("empty Ollama triage content")
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("Ollama JSON was not an object")
    elapsed_ms = (time.monotonic() - started) * 1000.0
    logger.info(
        "AI triage Ollama request done alert_id=%s cache=%s duration_ms=%.0f model=%s",
        alert_id or "n/a",
        cache_status,
        elapsed_ms,
        model,
    )
    return parsed, {"model": model, "ollama_raw": raw, "duration_ms": elapsed_ms}


def _cache_row_to_result(row: Dict[str, Any]) -> Dict[str, Any]:
    scope = row.get("suggested_suppression_scope") or {}
    if isinstance(scope, str):
        try:
            scope = json.loads(scope)
        except (TypeError, ValueError):
            scope = {}
    return {
        "verdict": row["verdict"],
        "confidence": float(row["confidence"]),
        "summary": row["summary"],
        "recommended_action": row["recommended_action"],
        "suggested_suppression_scope": scope,
        "cached": True,
        "content_hash": row["content_hash"],
        "model": row.get("model"),
        "updated_at": str(row.get("updated_at") or "") or None,
    }


def get_cached_triage(alert_id: str, content_hash: str) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        """
        SELECT
          verdict, confidence, summary, recommended_action,
          suggested_suppression_scope, content_hash, model, updated_at
        FROM alert_ai_triage_cache
        WHERE alert_id = %s::uuid AND content_hash = %s
        LIMIT 1;
        """,
        (alert_id, content_hash),
    )
    if not row:
        return None
    return _cache_row_to_result(row)


def _write_cache(
    *,
    alert_id: str,
    tenant_id: str,
    content_hash: str,
    model: str,
    result: Dict[str, Any],
    raw_response: Optional[Dict[str, Any]],
) -> None:
    fetch_one_write(
        """
        INSERT INTO alert_ai_triage_cache (
          alert_id, tenant_id, content_hash, model,
          verdict, confidence, summary, recommended_action,
          suggested_suppression_scope, raw_response, updated_at
        )
        VALUES (
          %s::uuid, %s::uuid, %s, %s,
          %s, %s, %s, %s,
          %s::jsonb, %s::jsonb, now()
        )
        ON CONFLICT (alert_id, content_hash) DO UPDATE SET
          model = EXCLUDED.model,
          verdict = EXCLUDED.verdict,
          confidence = EXCLUDED.confidence,
          summary = EXCLUDED.summary,
          recommended_action = EXCLUDED.recommended_action,
          suggested_suppression_scope = EXCLUDED.suggested_suppression_scope,
          raw_response = EXCLUDED.raw_response,
          updated_at = now()
        RETURNING id::text;
        """,
        (
            alert_id,
            tenant_id,
            content_hash,
            model,
            result["verdict"],
            result["confidence"],
            result["summary"],
            result["recommended_action"],
            json.dumps(result["suggested_suppression_scope"]),
            json.dumps(raw_response or {}, default=str),
        ),
    )


def _attach_enrichment(result: Dict[str, Any], enrichment: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(enrichment.get("context_summary") or {})
    guardrails = enrichment.get("action_guardrails") or {}
    # Phase 3 inclusion rule wins over advisory guardrail queue_suggestion.
    ai_queue = compute_ai_queue(result.get("verdict") or "", float(result.get("confidence") or 0))
    summary["queue_suggestion"] = ai_queue
    vt = (enrichment.get("threat_intel") or {}).get("external_vt") or {}
    return {
        **result,
        "enrichment": enrichment,
        "context_summary": summary,
        "pre_score_hints": enrichment.get("pre_score_hints"),
        "action_rationale": guardrails.get("action_rationale"),
        "queue_suggestion": ai_queue,
        "ai_queue": ai_queue,
        "historical_fp_pressure": guardrails.get("historical_fp_pressure"),
        "vt": vt if isinstance(vt, dict) else {"status": "not_configured"},
    }


def run_tier1_triage(
    *,
    alert_id: str,
    tenant_id: str,
    alert: Dict[str, Any],
    customer_safe: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Return cached or freshly computed Tier-1 triage for one alert.
    Raises TimeoutError / RuntimeError on Ollama failure (caller maps to HTTP).
    Persists ai_verdict/ai_confidence/ai_queue; optional auto-close when flag on.
    """
    # Ensure tenant/id available for enrichment queries even if caller omitted them.
    alert_for_enrich = dict(alert)
    alert_for_enrich.setdefault("tenant_id", tenant_id)
    alert_for_enrich.setdefault("id", alert_id)
    alert_for_enrich.setdefault("alert_id", alert_id)

    enrichment = enrich_alert_context(alert_for_enrich, customer_safe=customer_safe)
    payload = build_triage_payload_from_alert(alert_for_enrich, customer_safe=customer_safe)
    # Cache key covers telemetry + enrichment snapshot so stale context refreshes.
    content_hash = build_content_hash(
        {"telemetry": payload, "enrichment": enrichment.get("context_summary")}
    )

    if not force:
        cached = get_cached_triage(alert_id, content_hash)
        if cached:
            logger.info(
                "AI triage cache hit alert_id=%s cache=hit duration_ms=0",
                alert_id,
            )
            attached = _attach_enrichment(cached, enrichment)
            ai_queue = attached.get("ai_queue")
            _persist_alert_ai_fields(
                alert_id=alert_id,
                verdict=str(attached["verdict"]),
                confidence=float(attached["confidence"]),
                ai_queue=ai_queue if isinstance(ai_queue, str) else None,
            )
            auto = _try_auto_close_low_risk(
                alert_id=alert_id,
                tenant_id=tenant_id,
                alert=alert_for_enrich,
                enrichment=enrichment,
                result=attached,
            )
            attached["auto_close"] = auto
            return attached

    parsed, meta = _call_ollama_chat(
        build_user_prompt(payload, enrichment), alert_id=alert_id, cache_status="miss"
    )
    result = _normalize_result(
        parsed, fallback_rule=str(payload.get("wazuh_rule_id") or "")
    )
    # Prefer alert process path when model omits it
    scope = result["suggested_suppression_scope"]
    if not scope.get("process_path"):
        scope["process_path"] = str(
            payload.get("file_path") or payload.get("process_name") or ""
        )
    if not scope.get("rule_id"):
        scope["rule_id"] = str(payload.get("wazuh_rule_id") or "")

    model = str(meta.get("model") or "")
    _write_cache(
        alert_id=alert_id,
        tenant_id=tenant_id,
        content_hash=content_hash,
        model=model,
        result=result,
        raw_response=meta.get("ollama_raw"),
    )
    attached = _attach_enrichment(
        {
            **result,
            "cached": False,
            "content_hash": content_hash,
            "model": model,
            "updated_at": None,
        },
        enrichment,
    )
    ai_queue = attached.get("ai_queue")
    _persist_alert_ai_fields(
        alert_id=alert_id,
        verdict=str(attached["verdict"]),
        confidence=float(attached["confidence"]),
        ai_queue=ai_queue if isinstance(ai_queue, str) else None,
    )
    auto = _try_auto_close_low_risk(
        alert_id=alert_id,
        tenant_id=tenant_id,
        alert=alert_for_enrich,
        enrichment=enrichment,
        result=attached,
    )
    attached["auto_close"] = auto
    return attached
