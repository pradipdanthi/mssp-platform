"""Isolation tests for the CLI execution layer (LOCAL, synthetic canaries, no real secrets, no network).

A stub "CLI" script stands in for the Cursor binary and reports exactly what it can see:
its argv, environment, working directory and whether canary files are readable. The real
CLI's own sandbox cannot be exercised here (it needs an authenticated model session); these
tests prove the properties this repository controls: argv, environment, workspace, redaction,
timeout cleanup, peer authentication and fail-closed behaviour.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.core import cli_exec  # noqa: E402

CANARY_KEY = "csk_CANARYCURSORKEY0123456789abcdefghijklmnop"
STUB = """#!/usr/bin/env python3
import json, os, sys, time
mode = os.environ.get("STUB_MODE", "")
if "--sleep" in sys.argv:
    time.sleep(60)
paths = ["/etc/shadow", os.environ.get("CANARY_FILE", "/nonexistent")]
readable = {}
for p in paths:
    try:
        open(p).read(1); readable[p] = True
    except Exception:
        readable[p] = False
report = {"argv": sys.argv[1:], "env_keys": sorted(os.environ.keys()), "cwd": os.getcwd(),
          "cwd_listing": sorted(os.listdir(".")), "has_key": "CURSOR_API_KEY" in os.environ,
          "readable": readable, "home": os.environ.get("HOME")}
print(json.dumps(report))
"""


def make_stub(directory: str, body: str = STUB) -> str:
    path = os.path.join(directory, "agent")
    with open(path, "w") as fh:
        fh.write(body)
    os.chmod(path, 0o755)
    return path


class RunLocalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stub = make_stub(self.tmp.name)
        self.home = os.path.join(self.tmp.name, "home")
        self.workspace = os.path.join(self.tmp.name, "ws")
        self.canary = os.path.join(self.tmp.name, "agent-secrets.env")
        with open(self.canary, "w") as fh:
            fh.write("SOC_AGENT_INGEST_TOKEN=CANARY\n")
        os.chmod(self.canary, 0o600)

    def run_stub(self, prompt="alert text", parent_env=None, **kw):
        parent = {"PATH": os.environ.get("PATH", ""), "CANARY_FILE": self.canary,
                  "SOC_AGENT_INGEST_TOKEN": "CANARY_INGEST_TOKEN_VALUE_0123456789",
                  "MSSP_CALLBACK_TOKEN": "CANARY_CALLBACK_TOKEN_VALUE_0123456789",
                  "DATABASE_PASSWORD": "canary-db-password", "AWS_SECRET_ACCESS_KEY": "canary-aws"}
        parent.update(parent_env or {})
        res = cli_exec.run_local(self.stub, prompt, home=self.home, workspace=self.workspace,
                                 api_key=CANARY_KEY, parent_env=parent, argv_override=[self.stub, "--stub"], **kw)
        return res, json.loads(res.stdout)

    def test_the_credential_is_never_on_the_command_line(self) -> None:
        _, report = self.run_stub()
        self.assertFalse(any(CANARY_KEY in a for a in report["argv"]))
        real = cli_exec.build_argv("/usr/bin/agent", model="auto")
        self.assertNotIn("--api-key", real)
        self.assertFalse(any(CANARY_KEY in a for a in real))

    def test_the_environment_is_an_allow_list_not_a_copy(self) -> None:
        _, report = self.run_stub()
        keys = set(report["env_keys"])
        for forbidden in ("SOC_AGENT_INGEST_TOKEN", "MSSP_CALLBACK_TOKEN", "DATABASE_PASSWORD", "AWS_SECRET_ACCESS_KEY", "CANARY_FILE"):
            self.assertNotIn(forbidden, keys)
        self.assertTrue(report["has_key"], "only the provider credential is passed")
        self.assertLessEqual(keys, {"PATH", "HOME", "XDG_CONFIG_HOME", "NO_COLOR", "NO_OPEN_BROWSER", "CURSOR_API_KEY", "LANG", "LC_ALL", "TZ",
                                    "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR", "LC_CTYPE", "PWD", "SHLVL", "_"})

    def test_the_cli_runs_in_an_empty_workspace_with_its_own_home(self) -> None:
        os.makedirs(self.workspace, exist_ok=True)
        _, report = self.run_stub()
        self.assertEqual(os.path.realpath(report["cwd"]), os.path.realpath(self.workspace))
        self.assertEqual(report["cwd_listing"], [])
        self.assertEqual(os.path.realpath(report["home"]), os.path.realpath(self.home))

    def test_no_key_is_passed_when_none_is_given(self) -> None:
        env = cli_exec.minimal_env(self.home, None, {"PATH": "/usr/bin", "CURSOR_API_KEY": CANARY_KEY})
        self.assertNotIn("CURSOR_API_KEY", env)

    def test_oversized_prompts_are_refused_before_spawning(self) -> None:
        with self.assertRaises(cli_exec.CliError) as ctx:
            cli_exec.run_local(self.stub, "x" * (cli_exec.MAX_PROMPT_BYTES + 1), home=self.home, workspace=self.workspace, api_key=None)
        self.assertEqual(ctx.exception.category, "prompt_too_large")

    def test_a_timeout_kills_the_whole_process_group(self) -> None:
        marker = os.path.join(self.tmp.name, "child.pid")
        script = f"""#!/usr/bin/env python3
import os, subprocess, sys, time
child = subprocess.Popen(["sleep", "60"])
open({marker!r}, "w").write(str(child.pid))
time.sleep(60)
"""
        stub = make_stub(self.tmp.name, script)
        started = time.monotonic()
        with self.assertRaises(cli_exec.CliError) as ctx:
            cli_exec.run_local(stub, "p", home=self.home, workspace=self.workspace, api_key=None, timeout=2, argv_override=[stub])
        self.assertEqual(ctx.exception.category, "timeout")
        self.assertLess(time.monotonic() - started, 15)
        time.sleep(0.3)
        pid = int(open(marker).read())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)  # the grandchild did not survive the timeout

    def test_stderr_is_redacted_and_timings_are_recorded(self) -> None:
        script = f"""#!/usr/bin/env python3
import sys
sys.stderr.write("auth failed for key {CANARY_KEY} Bearer abcdefghijklmnop.qrstuvwxyz\\n")
sys.exit(3)
"""
        stub = make_stub(self.tmp.name, script)
        res = cli_exec.run_local(stub, "p", home=self.home, workspace=self.workspace, api_key=CANARY_KEY, argv_override=[stub])
        self.assertEqual(res.rc, 3)
        self.assertNotIn(CANARY_KEY, res.stderr)
        self.assertNotIn("abcdefghijklmnop.qrstuvwxyz", res.stderr)
        for key in ("cli_spawn", "cli_first_output", "cli_total"):
            self.assertIn(key, res.timings)
            self.assertGreaterEqual(res.timings[key], 0)

    def test_a_sandbox_restriction_is_a_visible_degraded_result_not_a_retry(self) -> None:
        import re

        auth = re.compile(r"unauthori[sz]ed")
        for text in ("Error: sandbox failed to start: operation not permitted", "tool call blocked by policy"):
            res = cli_exec.CliResult(rc=1, stdout="", stderr=text)
            category, _ = cli_exec.classify_failure(res, auth)
            self.assertEqual(category, "sandbox_blocked", text)
        self.assertEqual(cli_exec.classify_failure(cli_exec.CliResult(1, "", "401 unauthorized"), auth)[0], "auth_failure")

    def test_unsandboxed_mode_cannot_be_requested_by_accident(self) -> None:
        self.assertIn("enabled", cli_exec.build_argv("/x", sandbox="bogus"))
        self.assertIn("enabled", cli_exec.build_argv("/x", sandbox="enabled"))


class RunnerTests(unittest.TestCase):
    """The runner service end to end over a real Unix socket, with the stub CLI."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        base = cls.tmp.name
        cls.stub = make_stub(base)
        env = {
            "TIA_RUNNER_SOCKET": os.path.join(base, "r.sock"),
            "TIA_RUNNER_HOME": os.path.join(base, "home"),
            "TIA_RUNNER_WORKSPACE": os.path.join(base, "ws"),
            "TIA_RUNNER_ALLOWED_UID": str(os.getuid()),
        }
        os.environ.update(env)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runner"))
        import importlib

        import tia_cli_runner as runner

        cls.runner = importlib.reload(runner)
        cls.runner.prepare_directories()
        cls.sock_path = env["TIA_RUNNER_SOCKET"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def start(self, uid=None, parallel=2, key=CANARY_KEY):
        # argv_override is not exposed over the socket, so point the runner at a stub that ignores args.
        server = self.runner.RunnerServer(self.sock_path, os.getuid() if uid is None else uid, key, self.stub, parallel)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        return server

    def test_ping_reports_ready_and_the_cli_config_denies_tools(self) -> None:
        self.start()
        ok, detail = cli_exec.runner_ping(self.sock_path)
        self.assertEqual((ok, detail), (True, "ready"))
        cfg = json.load(open(os.path.join(os.environ["TIA_RUNNER_HOME"], ".cursor", "cli-config.json")))
        for rule in ("Shell(*)", "Write(**)", "Read(**)", "WebFetch(*)", "Mcp(*)"):
            self.assertIn(rule, cfg["permissions"]["deny"])
        self.assertEqual(cfg["sandbox"]["mode"], "enabled")

    def test_ping_reports_not_ready_without_a_credential(self) -> None:
        self.start(key="")
        self.assertEqual(cli_exec.runner_ping(self.sock_path), (False, "CURSOR_API_KEY missing"))

    def test_a_run_goes_through_with_the_stub_and_returns_stdout_and_timings(self) -> None:
        self.start()
        res = cli_exec.run_via_runner(self.sock_path, "synthetic alert", model="", timeout=20)
        self.assertEqual(res.rc, 0)
        report = json.loads(res.stdout)
        self.assertTrue(report["has_key"])
        self.assertNotIn("--api-key", report["argv"])
        self.assertEqual(report["cwd_listing"], [])
        self.assertIn("runner_connect", res.timings)

    def test_a_peer_with_the_wrong_uid_is_rejected(self) -> None:
        self.start(uid=os.getuid() + 12345)
        with self.assertRaises(cli_exec.CliError) as ctx:
            cli_exec.run_via_runner(self.sock_path, "x", model="", timeout=10)
        self.assertEqual(ctx.exception.category, "forbidden")
        self.assertEqual(cli_exec.runner_ping(self.sock_path)[0], False)

    def test_an_unreachable_runner_is_a_visible_failure(self) -> None:
        with self.assertRaises(cli_exec.CliError) as ctx:
            cli_exec.run_via_runner(os.path.join(self.tmp.name, "absent.sock"), "x", model="", timeout=5)
        self.assertEqual(ctx.exception.category, "runner_unavailable")

    def test_capacity_is_bounded(self) -> None:
        slow = make_stub(self.tmp.name, "#!/usr/bin/env python3\nimport time\ntime.sleep(3)\nprint('{}')\n")
        server = self.runner.RunnerServer(self.sock_path, os.getuid(), CANARY_KEY, slow, 1)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        first = threading.Thread(target=lambda: cli_exec.run_via_runner(self.sock_path, "a", model="", timeout=20))
        first.start()
        time.sleep(0.6)
        with self.assertRaises(cli_exec.CliError) as ctx:
            cli_exec.run_via_runner(self.sock_path, "b", model="", timeout=20)
        self.assertEqual(ctx.exception.category, "runner_busy")
        first.join()

    def test_the_socket_is_not_world_accessible(self) -> None:
        self.start()
        mode = stat.S_IMODE(os.stat(self.sock_path).st_mode)
        self.assertEqual(mode & 0o007, 0)

    def test_a_malformed_request_is_refused(self) -> None:
        self.start()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.sock_path)
        s.sendall(struct.pack(">I", 10) + b"not json!!!")
        reply = cli_exec.recv_message(s, 1 << 20)
        s.close()
        self.assertEqual(reply.get("category"), "bad_request")


class AgentTokenTests(unittest.TestCase):
    def test_the_placeholder_token_is_refused(self) -> None:
        from fastapi import HTTPException

        from app import config, main

        for token in ("change-me-soc-ingest", "", "short"):
            with unittest.mock.patch.dict(os.environ, {"SOC_AGENT_INGEST_TOKEN": token}):
                config.settings.cache_clear()
                with self.assertRaises(HTTPException) as ctx:
                    main.require_token(token or None)
                self.assertEqual(ctx.exception.status_code, 503)
        config.settings.cache_clear()
        good = "g" * 40
        with unittest.mock.patch.dict(os.environ, {"SOC_AGENT_INGEST_TOKEN": good}):
            config.settings.cache_clear()
            main.require_token(good)
            with self.assertRaises(HTTPException) as ctx:
                main.require_token("w" * 40)
            self.assertEqual(ctx.exception.status_code, 401)
        config.settings.cache_clear()


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
