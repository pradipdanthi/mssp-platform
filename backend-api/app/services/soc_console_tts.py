"""Optional neural TTS for Tia spoken replies (OpenAI-compatible).

If TIA_TTS_ENABLED is not true, or key/base missing, callers should fall back
to browser speechSynthesis with a preferred female English voice.
"""

from __future__ import annotations

import base64
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def tts_configured() -> bool:
    flag = (os.getenv("TIA_TTS_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")
    key = (os.getenv("TIA_TTS_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    return flag and bool(key)


def synthesize_tia_speech(text: str) -> Optional[Dict[str, Any]]:
    """Return {audio_base64, content_type, provider} or None if unavailable."""
    if not tts_configured():
        return None
    cleaned = (text or "").strip()[:900]
    if len(cleaned) < 2:
        return None

    base = (
        os.getenv("TIA_TTS_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    key = (os.getenv("TIA_TTS_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    model = (os.getenv("TIA_TTS_MODEL") or "gpt-4o-mini-tts").strip()
    voice = (os.getenv("TIA_TTS_VOICE") or "coral").strip()

    body = {
        "model": model,
        "voice": voice,
        "input": cleaned,
        "format": "mp3",
    }
    req = urllib.request.Request(
        f"{base}/audio/speech",
        data=__import__("json").dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            audio = resp.read()
            ctype = resp.headers.get("Content-Type") or "audio/mpeg"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        logger.warning("Tia TTS HTTP %s: %s", exc.code, detail)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tia TTS failed: %s", exc)
        return None

    if not audio:
        return None
    return {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "content_type": ctype,
        "provider": "openai-tts",
        "voice": voice,
    }
