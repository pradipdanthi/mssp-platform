import os
from functools import lru_cache


@lru_cache
def settings() -> dict:
    return {
        "ingest_token": os.environ.get("SOC_AGENT_INGEST_TOKEN", "change-me-soc-ingest"),
        "audit_log": os.environ.get(
            "SOC_AGENT_AUDIT_LOG", "/var/log/soc-agent/audit.log"
        ),
        "dossier_dir": os.environ.get(
            "SOC_AGENT_DOSSIER_DIR", "/var/lib/soc-agent/dossiers"
        ),
        "listen_port": int(os.environ.get("SOC_AGENT_PORT", "8088")),
        "agent_name": os.environ.get("SOC_AGENT_NAME", "mssp-soc-agent"),
    }
