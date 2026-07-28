"""Read secrets from env or mounted files (never log values)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def read_secret(env_name: str, *file_candidates: str) -> Optional[str]:
    env = (os.getenv(env_name) or "").strip()
    if env:
        return env
    file_env = (os.getenv(f"{env_name}_FILE") or "").strip()
    candidates = []
    if file_env:
        candidates.append(file_env)
    candidates.extend(file_candidates)
    for path in candidates:
        try:
            text = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return None
