"""SOC Agent LLM — Cursor subscription CLI only (no lab Ollama).

Auth: CURSOR_API_KEY (Dashboard → Cursor Settings → API keys)
CLI:  `agent -p --mode ask` (installed as cursor-agent / agent)

Failure contract (prompt version soc-analyst-1):
  Every failure raises ProviderError with a category. Nothing here ever turns a
  failed call into a verdict. Callers decide what a failure means.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any

from app.core import cli_exec

PROMPT_VERSION = "soc-analyst-1"

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

# Failure categories reported to the control plane.
CAT_NOT_CONFIGURED = "not_configured"
CAT_BINARY_MISSING = "binary_missing"
CAT_AUTH = "auth_failure"
CAT_TIMEOUT = "timeout"
CAT_NONZERO_EXIT = "nonzero_exit"
CAT_EMPTY = "empty_output"
CAT_MALFORMED = "malformed_output"
CAT_MISSING_FIELDS = "missing_fields"
CAT_SANDBOX_BLOCKED = "sandbox_blocked"
CAT_RUNNER_UNAVAILABLE = "runner_unavailable"
CAT_RUNNER_BUSY = "runner_busy"
CAT_PROMPT_TOO_LARGE = "prompt_too_large"

_KNOWN_PROVIDER_CATEGORIES = frozenset(
    {
        CAT_NOT_CONFIGURED, CAT_BINARY_MISSING, CAT_AUTH, CAT_TIMEOUT, CAT_NONZERO_EXIT, CAT_EMPTY,
        CAT_MALFORMED, CAT_MISSING_FIELDS, CAT_SANDBOX_BLOCKED, CAT_RUNNER_UNAVAILABLE, CAT_RUNNER_BUSY,
        CAT_PROMPT_TOO_LARGE,
    }
)

_VERDICTS = {"benign": "Benign", "suspicious": "Suspicious", "critical": "Critical"}
_AUTH_RE = re.compile(
    r"(unauthori[sz]ed|invalid[ _-]?api[ _-]?key|authentication (failed|required|error)|"
    r"not (logged|signed) in|forbidden|\b40[13]\b|api key (is )?(invalid|expired|revoked))",
    re.IGNORECASE,
)
_TOKENISH_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")


class ProviderError(Exception):
    """A provider call that did not produce a validated result."""

    def __init__(self, category: str, message: str = "") -> None:
        super().__init__(f"{category}: {message}" if message else category)
        self.category = category
        self.message = message

    @property
    def timed_out(self) -> bool:
        return self.category == CAT_TIMEOUT


def redact(text: str, secrets: list[str] | None = None) -> str:
    """Remove the configured key and anything shaped like a long token."""
    return cli_exec.redact(text, secrets)


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ProviderError(CAT_EMPTY, "empty model output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError as exc:
            raise ProviderError(CAT_MALFORMED, "fenced block is not valid JSON") from exc
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ProviderError(CAT_MALFORMED, "no valid JSON object in output") from exc
    raise ProviderError(CAT_MALFORMED, "no JSON object in output")


def _plain_bool(value: Any) -> bool:
    return value is True


def validate_triage(parsed: Any) -> dict[str, Any]:
    """Return a normalized, whitelisted verdict or raise ProviderError.

    Unknown keys (for example a model-invented notification destination) are
    dropped, not forwarded.
    """
    if not isinstance(parsed, dict):
        raise ProviderError(CAT_MALFORMED, "model output is not a JSON object")

    missing: list[str] = []
    verdict_raw = parsed.get("verdict")
    verdict = _VERDICTS.get(str(verdict_raw or "").strip().lower())
    if verdict is None:
        missing.append("verdict")

    confidence_raw = parsed.get("confidence")
    confidence: float | None = None
    if isinstance(confidence_raw, bool) or confidence_raw is None:
        missing.append("confidence")
    else:
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            missing.append("confidence")
        else:
            if not 0.0 <= confidence <= 100.0:
                missing.append("confidence")

    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        missing.append("summary")

    if missing:
        raise ProviderError(CAT_MISSING_FIELDS, "missing or invalid: " + ", ".join(missing))

    pkg_in = parsed.get("action_package") if isinstance(parsed.get("action_package"), dict) else {}
    action_package = {
        "propose_edr_isolate": _plain_bool(pkg_in.get("propose_edr_isolate")),
        "propose_itdr_remediate": _plain_bool(pkg_in.get("propose_itdr_remediate")),
        "propose_case_note": pkg_in.get("propose_case_note") is not False,
        "propose_customer_recommendation": _plain_bool(pkg_in.get("propose_customer_recommendation")),
        "escalate_human": _plain_bool(pkg_in.get("escalate_human")),
        "customer_action_title": str(pkg_in.get("customer_action_title") or "")[:500],
        "customer_action_body": str(pkg_in.get("customer_action_body") or "")[:4000],
        "notes": str(pkg_in.get("notes") or "")[:2000],
    }
    actions = parsed.get("recommended_actions")
    mitre = parsed.get("mitre")
    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary.strip()[:4000],
        "customer_safe_summary": str(parsed.get("customer_safe_summary") or "")[:1000],
        "root_cause": str(parsed.get("root_cause") or "")[:2000],
        "mitre": [m for m in mitre if isinstance(m, dict)][:8] if isinstance(mitre, list) else [],
        "recommended_actions": [str(a)[:500] for a in actions][:10] if isinstance(actions, list) else [],
        "false_positive_likelihood": str(parsed.get("false_positive_likelihood") or "")[:16],
        "escalate_to_human": _plain_bool(parsed.get("escalate_to_human")),
        "action_package": action_package,
    }


class CursorAgentProvider:
    """Cursor subscription models via the headless CLI."""

    name = "cursor-agent"

    def __init__(self) -> None:
        self._cli_version: str | None = None

    def _binary(self) -> str | None:
        return shutil.which("cursor-agent") or shutil.which("agent")

    @staticmethod
    def _runner_socket() -> str:
        return (os.environ.get("TIA_CLI_RUNNER_SOCKET") or "").strip()

    @staticmethod
    def _runner_required() -> bool:
        return (os.environ.get("TIA_REQUIRE_CLI_RUNNER") or "").strip().lower() in ("1", "true", "yes", "on")

    def available(self) -> bool:
        sock = self._runner_socket()
        if sock:
            ok, _ = cli_exec.runner_ping(sock)
            return ok
        if self._runner_required():
            return False
        if not (os.environ.get("CURSOR_API_KEY") or "").strip():
            return False
        return bool(self._binary())

    def missing_reason(self) -> str:
        sock = self._runner_socket()
        if sock:
            ok, detail = cli_exec.runner_ping(sock)
            return "ok" if ok else f"CLI runner not ready ({detail})"
        if self._runner_required():
            return "TIA_REQUIRE_CLI_RUNNER is set but TIA_CLI_RUNNER_SOCKET is not configured"
        if not (os.environ.get("CURSOR_API_KEY") or "").strip():
            return "CURSOR_API_KEY not set (paste from Cursor Dashboard → API keys)"
        if not self._binary():
            return "cursor-agent CLI not installed (curl https://cursor.com/install | bash)"
        return "ok"

    def cli_version(self) -> str:
        """Installed CLI version, or 'unknown'. Cached for the process lifetime."""
        if self._cli_version is not None:
            return self._cli_version
        binary = self._binary()
        version = "unknown"
        if self._runner_socket():
            version = cli_exec.runner_version(self._runner_socket())
            if version != "unknown":
                self._cli_version = version
            return version
        if binary:
            try:
                proc = subprocess.run(  # noqa: S603
                    [binary, "--version"], capture_output=True, text=True, timeout=10
                )
                first = (proc.stdout or "").strip().splitlines()
                if proc.returncode == 0 and first:
                    version = first[0][:64]
            except Exception:  # noqa: BLE001
                version = "unknown"
        self._cli_version = version
        return version

    def provenance(self) -> dict[str, Any]:
        """What actually ran. The resolved model is not reported by this CLI mode."""
        selector = (os.environ.get("CURSOR_AGENT_MODEL") or "").strip()
        return {
            "provider": self.name,
            "model_selector": selector or None,
            "resolved_model": "unknown",
            "cli_version": self.cli_version(),
            "prompt_version": PROMPT_VERSION,
        }

    def _invoke(self, full_prompt: str, *, request_id: str = "") -> tuple[str, dict[str, Any]]:
        """Run the CLI through the runner (production) or locally (development only)."""
        model = (os.environ.get("CURSOR_AGENT_MODEL") or "").strip()
        timeout = int(os.environ.get("SOC_AGENT_LLM_TIMEOUT", "180"))
        sock = self._runner_socket()
        started = time.monotonic()
        api_key = ""
        try:
            if sock:
                result = cli_exec.run_via_runner(sock, full_prompt, model=model, timeout=timeout, request_id=request_id)
            else:
                if self._runner_required():
                    raise ProviderError(CAT_NOT_CONFIGURED, "CLI runner required but not configured")
                binary = self._binary()
                if not binary:
                    raise ProviderError(CAT_BINARY_MISSING, "cursor-agent binary not found on PATH")
                api_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
                if not api_key:
                    raise ProviderError(CAT_NOT_CONFIGURED, "CURSOR_API_KEY missing")
                home = os.environ.get("TIA_CLI_HOME", "/var/lib/soc-agent/cli-home")
                workspace = os.environ.get("SOC_AGENT_WORKSPACE_EMPTY", "/var/lib/soc-agent/cli-workspace")
                result = cli_exec.run_local(
                    binary, full_prompt, model=model, sandbox=(os.environ.get("TIA_CLI_SANDBOX") or "enabled"),
                    timeout=timeout, home=home, workspace=workspace, api_key=api_key,
                )
        except cli_exec.CliError as exc:
            raise ProviderError(exc.category if exc.category in _KNOWN_PROVIDER_CATEGORIES else CAT_NONZERO_EXIT, exc.message) from exc
        duration_ms = int((time.monotonic() - started) * 1000)

        if result.rc != 0:
            category, detail = cli_exec.classify_failure(result, _AUTH_RE)
            raise ProviderError(category, detail)
        if not result.stdout.strip():
            raise ProviderError(CAT_EMPTY, "empty model output")
        meta = self.provenance()
        meta.update({"rc": result.rc, "duration_ms": duration_ms, "timings": result.timings})
        return result.stdout, meta

    def complete(self, prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
        full = (
            f"{SOC_ANALYST_SYSTEM}\n\nALERT CONTEXT:\n{prompt}\n\n"
            "Return ONLY the JSON object. No prose outside JSON."
        )
        stdout, meta = self._invoke(full)
        verdict = validate_triage(_extract_json(stdout))
        return verdict, meta

    def chat_text(self, system: str, user: str) -> tuple[str, dict[str, Any]]:
        """Free-form analyst chat (plain text answer, not triage JSON)."""
        full = (
            f"{system.strip()}\n\nANALYST QUESTION / CONTEXT:\n{user.strip()}\n\n"
            "Answer in clear prose for a human SOC analyst."
        )
        stdout, meta = self._invoke(full)
        meta["mode"] = "chat"
        return stdout.strip(), meta


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
            raise ProviderError(
                CAT_BINARY_MISSING if not self.cursor._binary() else CAT_NOT_CONFIGURED,
                self.cursor.missing_reason(),
            )
        return self.cursor.complete(prompt)

    def chat(self, system: str, user: str) -> tuple[str, dict[str, Any]]:
        if not self.cursor.available():
            raise ProviderError(
                CAT_BINARY_MISSING if not self.cursor._binary() else CAT_NOT_CONFIGURED,
                self.cursor.missing_reason(),
            )
        return self.cursor.chat_text(system, user)
