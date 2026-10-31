"""Redact secrets that appear in HTTP access-log paths (ingress tokens, etc.)."""

from __future__ import annotations

import logging
import re

# Wazuh instant-ingress token is the final path segment of the hook URL.
_WAZUH_HOOK_RE = re.compile(
    r"(/integrations/soc/hooks/wazuh/)[^/?\s]+",
    re.IGNORECASE,
)
# Other keyed hooks that embed secrets in the path.
_GENERIC_HOOK_RE = re.compile(
    r"(/integrations/(?:vuln|easm|soc)/hooks?/[^/\s]+/)[^/?\s]+",
    re.IGNORECASE,
)


def redact_access_path(message: str) -> str:
    out = _WAZUH_HOOK_RE.sub(r"\1<redacted>", message)
    out = _GENERIC_HOOK_RE.sub(r"\1<redacted>", out)
    return out


class AccessLogRedactFilter(logging.Filter):
    """Apply path redaction to uvicorn/gunicorn access log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = redact_access_path(record.msg)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(
                        redact_access_path(a) if isinstance(a, str) else a
                        for a in record.args
                    )
                elif isinstance(record.args, dict):
                    record.args = {
                        k: redact_access_path(v) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
        except Exception:  # noqa: BLE001
            return True
        return True


def install_access_log_redaction() -> None:
    filt = AccessLogRedactFilter()
    for name in ("uvicorn.access", "gunicorn.access", "uvicorn", "gunicorn"):
        logging.getLogger(name).addFilter(filt)
