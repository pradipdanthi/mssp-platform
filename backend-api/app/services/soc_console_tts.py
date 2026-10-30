"""Tia spoken voice.

Default is a neural English voice (no API key). A configured OpenAI-compatible
TTS endpoint is used instead when TIA_TTS_ENABLED and a key are set.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_EDGE_VOICE = "en-US-AriaNeural"
_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_MAX = 32


def _openai_ready() -> bool:
    flag = (os.getenv("TIA_TTS_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")
    key = (os.getenv("TIA_TTS_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    return flag and bool(key)


def _edge_voice() -> str:
    raw = (os.getenv("TIA_EDGE_VOICE") or "").strip()
    if raw:
        return raw
    other = (os.getenv("TIA_TTS_VOICE") or "").strip()
    if "Neural" in other:
        return other
    return _EDGE_VOICE


def tts_configured() -> bool:
    if _openai_ready():
        return True
    try:
        import edge_tts  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _openai_speech(cleaned: str) -> Optional[Dict[str, Any]]:
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
        with urllib.request.urlopen(req, timeout=20) as resp:
            audio = resp.read()
            ctype = resp.headers.get("Content-Type") or "audio/mpeg"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        logger.warning("Tia TTS HTTP %s: %s", exc.code, detail)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tia OpenAI TTS failed: %s", exc)
        return None
    if not audio:
        return None
    return {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "content_type": ctype,
        "provider": "openai-tts",
        "voice": voice,
    }


def _edge_speech(cleaned: str) -> Optional[Dict[str, Any]]:
    import edge_tts

    voice = _edge_voice()

    async def _run() -> bytes:
        com = edge_tts.Communicate(cleaned, voice)
        chunks: list[bytes] = []
        async for chunk in com.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                chunks.append(chunk["data"])
        return b"".join(chunks)

    try:
        audio = asyncio.run(asyncio.wait_for(_run(), timeout=12))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tia neural voice failed: %s", exc)
        return None
    if not audio:
        return None
    return {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "content_type": "audio/mpeg",
        "provider": "neural-voice",
        "voice": voice,
    }


def _cache_key(cleaned: str) -> str:
    voice = _edge_voice() if not _openai_ready() else (os.getenv("TIA_TTS_VOICE") or "coral")
    provider = "openai-tts" if _openai_ready() else "neural-voice"
    digest = hashlib.sha256(f"{provider}\0{voice}\0{cleaned}".encode("utf-8")).hexdigest()
    return digest


def synthesize_tia_speech(text: str) -> Optional[Dict[str, Any]]:
    """Return {audio_base64, content_type, provider, synthesis_ms, cached} or None."""
    cleaned = (text or "").strip()[:500]
    if len(cleaned) < 2:
        return None
    key = _cache_key(cleaned)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit:
            out = dict(hit)
            out["cached"] = True
            out["synthesis_ms"] = 0
            return out
    started = time.monotonic()
    spoken: Optional[Dict[str, Any]] = None
    if _openai_ready():
        spoken = _openai_speech(cleaned)
    if spoken is None:
        spoken = _edge_speech(cleaned)
    if not spoken:
        return None
    spoken["synthesis_ms"] = int((time.monotonic() - started) * 1000)
    spoken["cached"] = False
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = {k: v for k, v in spoken.items() if k not in ("synthesis_ms", "cached")}
    return spoken
