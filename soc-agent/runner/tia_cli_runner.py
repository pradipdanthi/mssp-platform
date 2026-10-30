"""tia-cli-runner: runs the Cursor headless CLI for the SOC agent under its own identity.

Runs as the unprivileged ``tia-analyst`` user inside the sandbox declared in
``deploy/tia-cli-runner.service``. It listens on a Unix socket, accepts a request only
from the SOC agent's uid (SO_PEERCRED), and never sees the agent's ingest or callback
secrets. It holds the Cursor credential (``CURSOR_API_KEY``, loaded by systemd from a
root-owned credential file) and starts the CLI in an empty workspace with an allow-listed
environment.

Protocol and execution helpers live in ``app/core/cli_exec.py`` (shared with the agent).

Environment
  TIA_RUNNER_SOCKET        socket path (default /run/tia-cli-runner/runner.sock)
  TIA_RUNNER_ALLOWED_UID   uid allowed to connect (required)
  TIA_RUNNER_SOCKET_GROUP  group that owns the socket (so the agent user can connect)
  TIA_RUNNER_HOME          CLI home (default /var/lib/tia-cli-runner/home)
  TIA_RUNNER_WORKSPACE     empty working directory (default /var/lib/tia-cli-runner/workspace)
  TIA_RUNNER_MAX_PARALLEL  concurrent CLI runs (default 2)
  CURSOR_API_KEY           provider credential (from systemd LoadCredential / EnvironmentFile)
  TIA_CLI_SANDBOX          enabled (default) | disabled   (disabled is refused unless TIA_ALLOW_UNSANDBOXED=1)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import socketserver
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.core import cli_exec  # noqa: E402

LOG = logging.getLogger("tia-cli-runner")

SOCKET_PATH = os.environ.get("TIA_RUNNER_SOCKET", "/run/tia-cli-runner/runner.sock")
HOME = os.environ.get("TIA_RUNNER_HOME", "/var/lib/tia-cli-runner/home")
WORKSPACE = os.environ.get("TIA_RUNNER_WORKSPACE", "/var/lib/tia-cli-runner/workspace")

# CLI permission policy written into the runner's own CLI home. The analysis task needs
# no shell, no file writes and no network fetches from the model. Entry syntax follows the
# installed CLI's cli-config.json ("Shell(ls)" style). NOTE: wildcard semantics are not
# verifiable without an authenticated CLI; the OS-level unit sandbox is the real boundary.
CLI_CONFIG = {
    "version": 1,
    "permissions": {
        "allow": [],
        "deny": ["Shell(*)", "Write(**)", "Read(**)", "WebFetch(*)", "Mcp(*)"],
    },
    "approvalMode": "allowlist",
    "sandbox": {"mode": "enabled", "networkAccess": "user_config_with_defaults"},
}


def allowed_uid() -> int:
    raw = os.environ.get("TIA_RUNNER_ALLOWED_UID", "")
    if not raw.isdigit():
        raise SystemExit("TIA_RUNNER_ALLOWED_UID must be set to the SOC agent's numeric uid")
    return int(raw)


def sandbox_mode() -> str:
    mode = (os.environ.get("TIA_CLI_SANDBOX") or "enabled").strip().lower()
    if mode == "disabled" and os.environ.get("TIA_ALLOW_UNSANDBOXED") != "1":
        LOG.error("TIA_CLI_SANDBOX=disabled refused without TIA_ALLOW_UNSANDBOXED=1; using enabled")
        return "enabled"
    return "enabled" if mode != "disabled" else "disabled"


def prepare_directories() -> None:
    os.makedirs(HOME, mode=0o700, exist_ok=True)
    os.makedirs(WORKSPACE, mode=0o700, exist_ok=True)
    cfg_dir = os.path.join(HOME, ".cursor")
    os.makedirs(cfg_dir, mode=0o700, exist_ok=True)
    with open(os.path.join(cfg_dir, "cli-config.json"), "w", encoding="utf-8") as fh:
        json.dump(CLI_CONFIG, fh, indent=2)
    # The workspace must stay empty: nothing in it for the model to read or alter.
    for name in os.listdir(WORKSPACE):
        path = os.path.join(WORKSPACE, name)
        shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) else os.unlink(path)


class Handler(socketserver.BaseRequestHandler):
    server: "RunnerServer"

    def handle(self) -> None:
        sock: socket.socket = self.request
        sock.settimeout(30)
        creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", creds)
        if uid != self.server.allowed_uid:
            LOG.warning("rejected connection from uid=%s", uid)
            cli_exec.send_message(sock, {"error": "peer not permitted", "category": "forbidden"})
            return
        try:
            request = cli_exec.recv_message(sock, cli_exec.MAX_PROMPT_BYTES + 4096)
        except Exception:  # noqa: BLE001
            cli_exec.send_message(sock, {"error": "bad request", "category": "bad_request"})
            return
        op = request.get("op")
        if op == "ping":
            ok = bool(self.server.api_key) and bool(self.server.binary)
            detail = "ready" if ok else ("CURSOR_API_KEY missing" if not self.server.api_key else "CLI not found")
            cli_exec.send_message(sock, {"ok": ok, "detail": detail, "cli_version": self.server.cli_version})
            return
        if op != "run":
            cli_exec.send_message(sock, {"error": "unknown operation", "category": "bad_request"})
            return
        prompt = str(request.get("prompt") or "")
        model = str(request.get("model") or "")[:100]
        timeout = max(5, min(int(request.get("timeout") or 180), 600))
        request_id = str(request.get("request_id") or "")[:64]
        if not self.server.slots.acquire(blocking=False):
            cli_exec.send_message(sock, {"error": "runner at capacity", "category": "runner_busy"})
            return
        started = time.monotonic()
        try:
            result = cli_exec.run_local(
                self.server.binary or "",
                prompt,
                model=model,
                sandbox=sandbox_mode(),
                timeout=timeout,
                home=HOME,
                workspace=WORKSPACE,
                api_key=self.server.api_key,
            )
            LOG.info("run request=%s rc=%s total_ms=%.0f", request_id, result.rc, (time.monotonic() - started) * 1000)
            cli_exec.send_message(
                sock,
                {"rc": result.rc, "stdout": result.stdout, "stderr": result.stderr, "timings": result.timings},
            )
        except cli_exec.CliError as exc:
            LOG.warning("run request=%s failed category=%s", request_id, exc.category)
            cli_exec.send_message(sock, {"error": exc.message or exc.category, "category": exc.category})
        except Exception as exc:  # noqa: BLE001
            LOG.exception("run request=%s crashed", request_id)
            cli_exec.send_message(sock, {"error": type(exc).__name__, "category": "nonzero_exit"})
        finally:
            self.server.slots.release()


def _cli_version(binary: str | None) -> str:
    if not binary:
        return "unknown"
    try:
        import subprocess

        proc = subprocess.run(  # noqa: S603
            [binary, "--version"], capture_output=True, text=True, timeout=10,
            env=cli_exec.minimal_env(HOME, None), cwd=WORKSPACE, stdin=subprocess.DEVNULL,
        )
        first = (proc.stdout or "").strip().splitlines()
        return first[0][:64] if proc.returncode == 0 and first else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


class RunnerServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, uid: int, api_key: str, binary: str | None, parallel: int) -> None:
        self.allowed_uid = uid
        self.api_key = api_key
        self.binary = binary
        self.slots = threading.BoundedSemaphore(parallel)
        self.cli_version = _cli_version(binary)
        if os.path.exists(path):
            os.unlink(path)
        super().__init__(path, Handler)
        group = os.environ.get("TIA_RUNNER_SOCKET_GROUP", "").strip()
        if group:
            shutil.chown(path, group=group)
        os.chmod(path, 0o660)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    prepare_directories()
    api_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    binary = shutil.which("cursor-agent") or shutil.which("agent")
    if not api_key:
        LOG.error("CURSOR_API_KEY is not set: runner will report not ready")
    server = RunnerServer(
        SOCKET_PATH, allowed_uid(), api_key, binary, int(os.environ.get("TIA_RUNNER_MAX_PARALLEL", "2"))
    )
    # The credential stays only in this process's memory from here on.
    os.environ.pop("CURSOR_API_KEY", None)
    LOG.info("listening on %s (sandbox=%s)", SOCKET_PATH, sandbox_mode())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
