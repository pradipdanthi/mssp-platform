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

SOC_ANALYST_SYSTEM = """You are an enterprise-class MSSP MDR/XDR SOC analyst (Tier-1/Tier-2 expert) for Kevantic NikTiar.
You assess ALL alert families: Silver ITDR (Okta/Entra/AD), Gold EDR/vuln/EASM, Platinum NDR/DFIR/threat-intel, and Secure Edge WAF/bot/DDoS events.
Analyze alert + enrichment. Respond with ONLY valid JSON (no markdown fences):
{
  "verdict": "Benign" | "Suspicious" | "Critical",
  "confidence": 0-100,
  "summary": "plain English one paragraph for a human SOC analyst",
  "customer_safe_summary": "short non-technical summary safe for the customer portal",
  "root_cause": "likely root cause hypothesis grounded in evidence",
  "mitre": [{"technique_id": "Txxxx", "technique_name": "..."}],
  "recommended_actions": ["action 1", "action 2"],
  "false_positive_likelihood": "low" | "medium" | "high",
  "escalate_to_human": true | false,
  "action_package": {
    "propose_edr_isolate": false,
    "propose_itdr_remediate": false,
    "propose_case_note": true,
    "propose_customer_recommendation": false,
    "escalate_human": false,
    "customer_action_title": "",
    "customer_action_body": "",
    "notes": "why these proposals — never claim auto-execution"
  }
}
Rules:
- Evidence discipline: do NOT invent IOCs, hosts, users, or MITRE techniques not supported by context.
- Prefer escalate_to_human=true when severity is high/critical and confidence < 80, or when containment is proposed.
- NEVER claim you isolated a host or disabled a user — only PROPOSE actions for human/SOAR approval.
- propose_edr_isolate only for credible Gold/Platinum host compromise with clear host evidence.
- propose_itdr_remediate only for credible identity compromise (MFA fatigue, impossible travel, account takeover).
- propose_customer_recommendation when the customer must take a concrete action; fill title/body in plain English.
- Secure Edge / WAF: focus on attacker intent, blocked vs bypassed, origin risk — not raw rule IDs.
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
            "--trust",
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

    def chat_text(self, system: str, user: str) -> tuple[str, dict[str, Any]]:
        """Free-form analyst chat (plain text answer, not triage JSON)."""
        binary = shutil.which("cursor-agent") or shutil.which("agent")
        if not binary:
            raise RuntimeError("cursor-agent binary not found on PATH")
        api_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("CURSOR_API_KEY missing")

        model = (os.environ.get("CURSOR_AGENT_MODEL") or "").strip()
        full = f"{system.strip()}\n\nANALYST QUESTION / CONTEXT:\n{user.strip()}\n\nAnswer in clear prose for a human SOC analyst."
        cmd = [
            binary,
            "-p",
            "--mode",
            "ask",
            "--output-format",
            "text",
            "--sandbox",
            "disabled",
            "--trust",
            "--api-key",
            api_key,
        ]
        if model:
            cmd.extend(["--model", model])
        cmd.append(full)

        env = os.environ.copy()
        env["CURSOR_API_KEY"] = api_key
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
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0 and not stdout:
            raise RuntimeError(
                f"cursor-agent rc={proc.returncode}: {(stderr or stdout)[:600]}"
            )
        return stdout, {
            "provider": self.name,
            "binary": binary,
            "model": model or "account_default",
            "rc": proc.returncode,
            "mode": "chat",
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

    def chat(self, system: str, user: str) -> tuple[str, dict[str, Any]]:
        if not self.cursor.available():
            raise RuntimeError(
                "Cursor LLM not ready: " + self.cursor.missing_reason()
            )
        return self.cursor.chat_text(system, user)
