#!/usr/bin/env bash
# Install the privilege-separated CLI runner and the hardened agent unit on VM 117.
# Review before running; run as root. It changes users, directories and systemd units on
# the machine it runs on, so it is a ROLLOUT step, never run by tests.
#
# It does not print, generate or move any credential: you place the Cursor key yourself
# (see the end of the output). Rollback: see docs/TIA_INVESTIGATION_STATUS.md.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
SRC="${SRC:-/opt/soc-agent}"

getent group tia-runner >/dev/null || groupadd --system tia-runner
getent passwd tia-analyst >/dev/null || useradd --system --home-dir /var/lib/tia-cli-runner --shell /usr/sbin/nologin --user-group tia-analyst
getent passwd soc-agent >/dev/null || useradd --system --home-dir /var/lib/soc-agent --shell /usr/sbin/nologin --user-group soc-agent
usermod -aG tia-runner soc-agent

install -d -m 0755 -o root -g root /opt/tia-cli-runner /opt/tia-cli-runner/runner /opt/tia-cli-runner/app /opt/tia-cli-runner/app/core
install -m 0644 "$SRC/runner/tia_cli_runner.py" /opt/tia-cli-runner/runner/tia_cli_runner.py
install -m 0644 "$SRC/app/core/cli_exec.py" /opt/tia-cli-runner/app/core/cli_exec.py
: > /opt/tia-cli-runner/app/__init__.py; : > /opt/tia-cli-runner/app/core/__init__.py

install -d -m 0750 -o root -g tia-analyst /etc/tia-cli-runner
install -d -m 0750 -o root -g soc-agent /etc/soc-agent /etc/soc-agent/tls
SOC_UID="$(id -u soc-agent)"
printf 'TIA_RUNNER_ALLOWED_UID=%s\n' "$SOC_UID" > /etc/tia-cli-runner/runner.env
chown root:tia-analyst /etc/tia-cli-runner/runner.env; chmod 0640 /etc/tia-cli-runner/runner.env

# Cursor CLI installed for the runner identity only (its own home, not secadmin's).
install -d -m 0700 -o tia-analyst -g tia-analyst /var/lib/tia-cli-runner /var/lib/tia-cli-runner/home /var/lib/tia-cli-runner/workspace
if ! runuser -u tia-analyst -- test -x /var/lib/tia-cli-runner/home/.local/bin/agent; then
  runuser -u tia-analyst -- env HOME=/var/lib/tia-cli-runner/home sh -c 'curl -fsSL https://cursor.com/install | bash'
fi

install -d -m 0750 -o soc-agent -g soc-agent /var/lib/soc-agent /var/log/soc-agent
chown -R soc-agent:soc-agent /opt/soc-agent/data 2>/dev/null || true

install -m 0644 "$SRC/deploy/tia-cli-runner.service" /etc/systemd/system/tia-cli-runner.service
install -m 0644 "$SRC/deploy/mssp-soc-agent.service" /etc/systemd/system/mssp-soc-agent.service
systemd-analyze verify /etc/systemd/system/tia-cli-runner.service /etc/systemd/system/mssp-soc-agent.service
systemctl daemon-reload

cat <<'MSG'

Installed. Remaining manual steps (nothing below is automated on purpose):
  1. Place the Cursor API key:   install -m 0600 -o root -g root /dev/stdin /etc/tia-cli-runner/cursor_api_key
     (paste the key, Ctrl-D). The agent user cannot read this file.
  2. Move the existing agent secrets to /etc/soc-agent/agent.env (root:soc-agent 0640) and REMOVE
     CURSOR_API_KEY from every agent-readable file, then rotate that key (see the rotation procedure).
  3. Generate TLS material:  OUT=/etc/soc-agent/tls AGENT_NAMES="<agent dns or ip>" ./scripts/tia_tls_setup.sh
  4. systemctl enable --now tia-cli-runner.service && systemctl enable --now mssp-soc-agent.service
  5. Verify: systemctl status ...; curl --cacert ca.crt https://<agent>:8443/health
MSG
