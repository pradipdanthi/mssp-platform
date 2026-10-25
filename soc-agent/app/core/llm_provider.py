"""SOC Agent LLM — Cursor subscription only (no lab Ollama).

Auth: CURSOR_API_KEY (Dashboard → Cursor Settings → API keys)
CLI:  `agent -p --mode ask` (installed as cursor-agent / agent)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

SOC_ANALYST_SYSTEM = """You are a certified MSSP Tier-1/Tier-2 SOC analyst working for Kevantic/NikTiar.
Analyze the alert + enrichment context. Respond with ONLY valid JSON (no markdown fences):
{
  "verdict": "Benign" | "Suspicious" | "Critical",
  "confidence": 0-100,
  "summary": "plain English one paragraph for a human SOC analyst",
  "root_cause": "likely root cause hypothesis",
  "mitre": [{"technique_id": "Txxxx", "technique_name": "..."}],
  "recommended_actions": ["action 1", "action 2"],
  "false_positive_likelihood": "low" | "medium" | "high",
  "escalate_to_human": true | false
}
Rules:
- Prefer escalate_to_human=true when severity is high/critical and confidence < 80.
- Do not invent IOCs that are not in the context.
- Map MITRE ATT&CK only when evidence supports it.
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty LLM response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"no JSON in LLM output: {text[:300]}")


class CursorAgentProvider:
    """Primary & only production driver — Cursor subscription models via CLI."""

    name = "cursor-agent"

    def available(self) -> bool:
        if not (os.environ.get("CURSOR_API_KEY") or "").strip():
            return False
        return bool(shutil.which("cursor-agent") or shutil.which("agent"))

    def missing_reason(self) -> str:
        if not (os.environ.get("CURSOR_API_KEY") or "").strip():
            return "CURSOR_API_KEY not set (paste from Cursor Dashboard → API keys)"
        if not (shutil.which("cursor-agent") or shutil.which("agent")):
            return "cursor-agent CLI not installed (curl https://cursor.com/install | bash)"
        return "ok"

    def complete(self, prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
        binary = shutil.which("cursor-agent") or shutil.which("agent")
        if not binary:
            raise RuntimeError("cursor-agent binary not found on PATH")
        api_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("CURSOR_API_KEY missing")

        model = (os.environ.get("CURSOR_AGENT_MODEL") or "").strip()
        full = (
            f"{SOC_ANALYST_SYSTEM}\n\nALERT CONTEXT:\n{prompt}\n\n"
            "Return ONLY the JSON object. No prose outside JSON."
        )
        cmd = [
            binary,
            "-p",
            "--mode",
            "ask",
            "--output-format",
            "text",
            "--sandbox",
            "disabled",
            "--api-key",
            api_key,
        ]
        if model:
            cmd.extend(["--model", model])
        cmd.append(full)

        env = os.environ.copy()
        env["CURSOR_API_KEY"] = api_key
        # Do not inherit lab Ollama endpoints into the CLI process
        env.pop("OLLAMA_HOST", None)
        env.pop("AI_ALERT_BASE_URL", None)

        timeout = int(os.environ.get("SOC_AGENT_LLM_TIMEOUT", "180"))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=os.environ.get("SOC_AGENT_WORKSPACE", "/opt/soc-agent"),
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode != 0 and not stdout.strip():
            raise RuntimeError(
                f"cursor-agent rc={proc.returncode}: {(stderr or stdout)[:600]}"
            )
        parsed = _extract_json(stdout)
        return parsed, {
            "provider": self.name,
            "binary": binary,
            "model": model or "account_default",
            "rc": proc.returncode,
        }


class LLMRouter:
    """Cursor subscription only — Ollama is intentionally excluded."""

    def __init__(self) -> None:
        self.cursor = CursorAgentProvider()

    def status(self) -> dict[str, Any]:
        return {
            "cursor": {
                "available": self.cursor.available(),
                "reason": self.cursor.missing_reason(),
            },
            "ollama": {
                "available": False,
                "reason": "disabled_for_soc_agent_use_control_plane_tier1_only",
            },
        }

    def triage(self, prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.cursor.available():
            raise RuntimeError(
                "Cursor LLM not ready: " + self.cursor.missing_reason()
            )
        return self.cursor.complete(prompt)
