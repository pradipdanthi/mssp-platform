import os
from functools import lru_cache


@lru_cache
def settings() -> dict:
    return {
        "ingest_token": os.environ.get("SOC_AGENT_INGEST_TOKEN", "change-me-soc-ingest"),
        "audit_log": os.environ.get(
            "SOC_AGENT_AUDIT_LOG", "/var/log/soc-agent/audit.log"
        ),
        "triage_audit_log": os.environ.get(
            "SOC_AGENT_TRIAGE_AUDIT_LOG", "/var/log/soc-agent/triage_audit.log"
        ),
        "dossier_dir": os.environ.get(
            "SOC_AGENT_DOSSIER_DIR", "/var/lib/soc-agent/dossiers"
        ),
        "listen_port": int(os.environ.get("SOC_AGENT_PORT", "8443")),
        "agent_name": os.environ.get("SOC_AGENT_NAME", "mssp-soc-agent"),
        "mssp_callback_url": (os.environ.get("MSSP_CALLBACK_URL") or "").rstrip("/"),
        "mssp_callback_token": (
            os.environ.get("MSSP_CALLBACK_TOKEN")
            or os.environ.get("SOC_AGENT_INGEST_TOKEN")
            or ""
        ).strip(),
    }
