"""Server-side speech-to-text for Tia mic (lab-safe; avoids Chrome Web Speech on self-signed TLS)."""

from __future__ import annotations

import base64
import io
import logging
import wave
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ~20s of 16-bit mono 16 kHz ≈ 640 KB; allow headroom for higher capture rates.
_MAX_WAV_BYTES = 3_500_000


def stt_available() -> bool:
    try:
        import speech_recognition  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _decode_wav(audio_base64: str) -> bytes:
    raw = (audio_base64 or "").strip()
    if not raw:
        raise ValueError("empty_audio")
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid_base64") from exc
    if len(data) < 44:
        raise ValueError("audio_too_short")
    if len(data) > _MAX_WAV_BYTES:
        raise ValueError("audio_too_large")
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("expected_wav")
    return data


def _wav_duration_seconds(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            return float(frames) / float(rate)
    except Exception:  # noqa: BLE001
        return 0.0


def transcribe_wav_base64(audio_base64: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Return (transcript_or_None, meta)."""
    if not stt_available():
        return None, {"ok": False, "reason": "stt_package_missing"}

    import speech_recognition as sr

    try:
        data = _decode_wav(audio_base64)
    except ValueError as exc:
        return None, {"ok": False, "reason": str(exc)}

    duration = _wav_duration_seconds(data)
    if duration < 0.35:
        return None, {"ok": False, "reason": "too_short", "duration_sec": duration}
    if duration > 25.0:
        return None, {"ok": False, "reason": "too_long", "duration_sec": duration}

    recognizer = sr.Recognizer()
    # Hands-free wake phrases are short ("Hi Tia"). adjust_for_ambient_noise
    # consumes leading audio and routinely destroys those clips → no_speech.
    recognizer.dynamic_energy_threshold = False
    recognizer.energy_threshold = 200
    try:
        with sr.AudioFile(io.BytesIO(data)) as source:
            if duration >= 2.2:
                recognizer.adjust_for_ambient_noise(
                    source, duration=min(0.2, duration / 8.0)
                )
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio, language="en-US")
    except sr.UnknownValueError:
        logger.info("Tia STT no_speech duration=%.2fs", duration)
        return None, {"ok": False, "reason": "no_speech", "duration_sec": duration}
    except sr.RequestError as exc:
        logger.warning("Tia STT upstream failed: %s", exc)
        return None, {"ok": False, "reason": "stt_upstream", "duration_sec": duration}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tia STT failed: %s", exc)
        return None, {"ok": False, "reason": "stt_failed", "duration_sec": duration}

    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return None, {"ok": False, "reason": "no_speech", "duration_sec": duration}
    logger.info("Tia STT ok duration=%.2fs text=%r", duration, cleaned[:120])
    return cleaned[:4000], {
        "ok": True,
        "provider": "google_web_speech",
        "duration_sec": round(duration, 2),
    }
