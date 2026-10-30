"""Execution of the Cursor headless CLI, locally or through the privilege-separated runner.

Why a separate runner
  The SOC agent service holds the ingest and callback secrets and talks to the control
  plane. The Cursor CLI reads untrusted alert text. Giving the CLI the same identity,
  environment and filesystem view as the agent service means a successful prompt
  injection could reach every secret the service has. In production the CLI therefore
  runs in a second service (``tia-cli-runner``) under its own unprivileged user, with its
  own systemd sandbox, and the agent talks to it over a Unix socket. The agent never
  holds the Cursor credential.

What this module guarantees (all covered by tests in ``tests/test_cli_exec.py``)
  * The credential is never placed on the command line.
  * The CLI environment is built from an allow-list, never copied from the parent.
  * The CLI runs in an empty workspace directory.
  * Output and errors are redacted before they leave this module.
  * A timeout kills the whole process group.
  * A restriction that blocks the call is reported as a degraded result
    (``sandbox_blocked``). There is no automatic retry with the sandbox disabled.

What it cannot guarantee
  The CLI needs the Cursor credential to authenticate, so the runner process (and the CLI
  it starts) can read it. Moving it into an environment variable does not remove that
  exposure; confinement is provided by the runner's unix user and unit sandbox, and the
  residual exposure is the runner identity itself. See docs/TIA_INVESTIGATION_STATUS.md.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# Environment variables the CLI may receive. Everything else is dropped.
ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "TZ", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR")

MAX_PROMPT_BYTES = 96 * 1024
MAX_OUTPUT_BYTES = 512 * 1024

SANDBOX_BLOCKED_RE = re.compile(
    r"(sandbox[^\n]{0,80}(denied|blocked|unavailable|not (supported|available)|failed)|"
    r"operation not permitted|permission denied by (policy|sandbox)|blocked by (policy|permissions))",
    re.IGNORECASE,
)
_TOKENISH_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")


class CliError(Exception):
    """A failed CLI execution with a category the caller maps to a ProviderError."""

    def __init__(self, category: str, message: str = "") -> None:
        super().__init__(f"{category}: {message}" if message else category)
        self.category = category
        self.message = message


@dataclass
class CliResult:
    rc: int
    stdout: str
    stderr: str
    timings: dict[str, float] = field(default_factory=dict)


def redact(text: str, secrets: list[str] | None = None) -> str:
    out = text or ""
    for secret in secrets or []:
        if secret and len(secret) >= 8:
            out = out.replace(secret, "<redacted>")
    out = _BEARER_RE.sub("Bearer <redacted>", out)
    return _TOKENISH_RE.sub("<redacted>", out)


def minimal_env(home: str, api_key: str | None, parent: dict[str, str] | None = None) -> dict[str, str]:
    """Allow-listed environment for the CLI. The key is passed only as CURSOR_API_KEY."""
    parent = os.environ if parent is None else parent
    env = {k: parent[k] for k in ENV_ALLOWLIST if k in parent}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env["HOME"] = home
    env["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
    env["NO_COLOR"] = "1"
    env["NO_OPEN_BROWSER"] = "1"
    if api_key:
        env["CURSOR_API_KEY"] = api_key
    return env


def build_argv(binary: str, *, model: str = "", sandbox: str = "enabled") -> list[str]:
    """Fixed argv. No credential, no prompt text (the prompt goes on stdin-free argv as one item)."""
    if sandbox not in ("enabled", "disabled"):
        sandbox = "enabled"
    argv = [binary, "-p", "--mode", "ask", "--output-format", "text", "--sandbox", sandbox, "--trust"]
    if model:
        argv.extend(["--model", model])
    return argv


def _kill_group(proc: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def run_local(
    binary: str,
    prompt: str,
    *,
    model: str = "",
    sandbox: str = "enabled",
    timeout: int = 180,
    home: str,
    workspace: str,
    api_key: str | None,
    parent_env: dict[str, str] | None = None,
    argv_override: list[str] | None = None,
) -> CliResult:
    """Run the CLI once. Records spawn, first-output and total durations (monotonic)."""
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise CliError("prompt_too_large", "prompt exceeds the allowed size")
    os.makedirs(workspace, exist_ok=True)
    os.makedirs(home, exist_ok=True)
    argv = (argv_override or build_argv(binary, model=model, sandbox=sandbox)) + [prompt]
    env = minimal_env(home, api_key, parent_env)
    t_spawn = time.monotonic()
    try:
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=workspace,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        raise CliError("nonzero_exit", redact(str(exc), [api_key or ""])[:200]) from exc
    spawned = time.monotonic()

    first_out: list[float] = []
    chunks: dict[str, list[bytes]] = {"out": [], "err": []}
    sizes = {"out": 0, "err": 0}

    def pump(stream, key: str) -> None:
        while True:
            data = stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
            if not data:
                return
            if key == "out" and not first_out:
                first_out.append(time.monotonic())
            if sizes[key] < MAX_OUTPUT_BYTES:
                chunks[key].append(data)
                sizes[key] += len(data)

    threads = [
        threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True),
    ]
    for t in threads:
        t.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_group(proc)
        raise CliError("timeout", f"no result within {timeout}s") from exc
    finally:
        for t in threads:
            t.join(timeout=2)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass
    done = time.monotonic()
    timings = {
        "cli_spawn": round((spawned - t_spawn) * 1000, 2),
        "cli_first_output": round(((first_out[0] if first_out else done) - spawned) * 1000, 2),
        "cli_total": round((done - spawned) * 1000, 2),
    }
    secrets = [api_key or ""]
    return CliResult(
        rc=proc.returncode,
        stdout=b"".join(chunks["out"]).decode("utf-8", "replace"),
        stderr=redact(b"".join(chunks["err"]).decode("utf-8", "replace"), secrets),
        timings=timings,
    )


def classify_failure(result: CliResult, auth_re: re.Pattern[str]) -> tuple[str, str]:
    """Map a non-zero CLI result to (category, redacted detail)."""
    blob = f"{result.stderr}\n{result.stdout}"
    if auth_re.search(blob):
        return "auth_failure", "provider rejected the credential"
    if SANDBOX_BLOCKED_RE.search(blob):
        return "sandbox_blocked", redact(result.stderr or result.stdout)[:200]
    return "nonzero_exit", f"rc={result.rc}: {redact(result.stderr or result.stdout).strip()[:300]}"


# ---------------------------------------------------------------------------
# Runner protocol: 4-byte big-endian length + JSON, over a Unix socket.
# ---------------------------------------------------------------------------


def _send(sock: socket.socket, obj: dict[str, Any]) -> None:
    raw = json.dumps(obj).encode("utf-8")
    sock.sendall(struct.pack(">I", len(raw)) + raw)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            raise ConnectionError("connection closed")
        buf += part
    return buf


def _recv(sock: socket.socket, limit: int) -> dict[str, Any]:
    (length,) = struct.unpack(">I", _recv_exact(sock, 4))
    if length > limit:
        raise ValueError("message too large")
    return json.loads(_recv_exact(sock, length).decode("utf-8"))


send_message = _send
recv_message = _recv


def run_via_runner(socket_path: str, prompt: str, *, model: str, timeout: int, request_id: str = "") -> CliResult:
    """Ask the privilege-separated runner to execute the CLI."""
    started = time.monotonic()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout + 20)
    try:
        sock.connect(socket_path)
        connect_ms = (time.monotonic() - started) * 1000
        _send(sock, {"op": "run", "prompt": prompt, "model": model, "timeout": timeout, "request_id": request_id})
        reply = _recv(sock, MAX_OUTPUT_BYTES + 64 * 1024)
    except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as exc:
        raise CliError("runner_unavailable", f"{type(exc).__name__}") from exc
    finally:
        sock.close()
    if reply.get("error"):
        raise CliError(str(reply.get("category") or "nonzero_exit"), str(reply.get("error"))[:300])
    timings = dict(reply.get("timings") or {})
    timings["runner_connect"] = round(connect_ms, 2)
    return CliResult(rc=int(reply.get("rc", 1)), stdout=str(reply.get("stdout") or ""), stderr=str(reply.get("stderr") or ""), timings=timings)


def runner_version(socket_path: str, timeout: float = 2.0) -> str:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(socket_path)
        _send(sock, {"op": "ping"})
        return str(_recv(sock, 64 * 1024).get("cli_version") or "unknown")[:64]
    except (OSError, ConnectionError, ValueError, json.JSONDecodeError):
        return "unknown"
    finally:
        sock.close()


def runner_ping(socket_path: str, timeout: float = 2.0) -> tuple[bool, str]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(socket_path)
        _send(sock, {"op": "ping"})
        reply = _recv(sock, 64 * 1024)
        return bool(reply.get("ok")), str(reply.get("detail") or "")
    except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as exc:
        return False, type(exc).__name__
    finally:
        sock.close()
