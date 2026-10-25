#!/usr/bin/env bash
# Install Cursor CLI + host systemd SOC agent (no Docker LLM; Cursor needs host CLI).
set -euo pipefail
cd /opt/soc-agent

echo "==> Install Cursor agent CLI"
curl -fsSL https://cursor.com/install | bash
export PATH="$HOME/.local/bin:$PATH"
command -v agent >/dev/null

echo "==> Python venv"
python3 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

sudo mkdir -p /var/log/soc-agent /var/lib/soc-agent/dossiers
sudo chown -R secadmin:secadmin /var/log/soc-agent /var/lib/soc-agent
mkdir -p /opt/soc-agent/data

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
fi

# Stop docker variant if running (host systemd owns :8443)
if command -v docker >/dev/null 2>&1; then
  sudo docker compose -f /opt/soc-agent/docker-compose.yml down 2>/dev/null || true
fi

sudo cp deploy/mssp-soc-agent.service /etc/systemd/system/mssp-soc-agent.service
sudo systemctl daemon-reload
sudo systemctl enable mssp-soc-agent.service
sudo systemctl restart mssp-soc-agent.service
sleep 2
systemctl --no-pager --full status mssp-soc-agent.service | head -20
curl -fsS http://127.0.0.1:8443/health || true
echo
echo "DONE. If health.llm.cursor.available=false, set CURSOR_API_KEY in /opt/soc-agent/.env and: sudo systemctl restart mssp-soc-agent"
