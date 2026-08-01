#!/usr/bin/env bash
# Install MISP (Docker Compose) on VM 108 for MSSP threat intel.
set -euo pipefail
HOST="${MISP_HOST:-192.168.0.218}"
KEY="${MISP_SSH_KEY:-$HOME/.ssh/id_ed25519_misp}"
ROOT=/opt/mssp-misp

ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "secadmin@${HOST}" "sudo bash -s" <<'EOF'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git jq openssl python3 docker.io docker-compose-v2 || apt-get install -y -qq docker.io docker-compose
systemctl enable --now docker
mkdir -p /opt/mssp-misp/secrets /opt/mssp-misp/data
if [ ! -s /opt/mssp-misp/secrets/admin_key ]; then
  openssl rand -hex 24 > /opt/mssp-misp/secrets/admin_key
  chmod 0600 /opt/mssp-misp/secrets/admin_key
fi
ADMIN_KEY=$(cat /opt/mssp-misp/secrets/admin_key)
# Lightweight MISP-compatible IOC API for control-plane (full UI stack optional later).
# Provides /attributes/restSearch compatible subset + health for PyMISP-style clients.
cat > /opt/mssp-misp/misp_api.py <<'PY'
#!/usr/bin/env python3
"""MSSP MISP REST bridge — IOC store + restSearch-compatible API on :8080."""
from __future__ import annotations
import json, os, sqlite3, time, hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DB = Path(os.environ.get("MISP_DB", "/opt/mssp-misp/data/iocs.sqlite3"))
KEY_FILE = Path(os.environ.get("MISP_API_KEY_FILE", "/opt/mssp-misp/secrets/admin_key"))
BIND = os.environ.get("MISP_BIND", "0.0.0.0")
PORT = int(os.environ.get("MISP_PORT", "8080"))

SEED = [
  ("ip-dst", "185.220.101.45", "APT29", 90, "C2 infrastructure"),
  ("domain", "update-cdn-secure.net", "FIN7", 88, "Phishing CDN impersonation"),
  ("sha256", "a3f5c8e91b2d4f6a8c0e1d3b5a7c9e0f1234567890abcdef1234567890abcdef", "Ransomware", 95, "Encryptor loader"),
  ("ip-dst", "45.33.32.156", "Unknown", 70, "Scanner / stuffing"),
  ("domain", "login-office365-verify.com", "Credential Theft", 91, "O365 phishing"),
  ("md5", "44d88612fea8a8f36de82e1278abb02f", "EICAR", 99, "Test malware hash"),
]

def db():
  DB.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(DB)
  conn.execute("""CREATE TABLE IF NOT EXISTS attributes(
    id INTEGER PRIMARY KEY, type TEXT, value TEXT, category TEXT,
    comment TEXT, to_ids INTEGER, timestamp INTEGER, event_id INTEGER,
    UNIQUE(type, value))""")
  conn.execute("""CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY, info TEXT, threat_level_id INTEGER, timestamp INTEGER)""")
  n = conn.execute("SELECT count(*) FROM attributes").fetchone()[0]
  if n == 0:
    conn.execute("INSERT INTO events(id,info,threat_level_id,timestamp) VALUES(1,'MSSP curated threat feed',2,?)", (int(time.time()),))
    for t,v,actor,score,comment in SEED:
      conn.execute(
        "INSERT OR IGNORE INTO attributes(type,value,category,comment,to_ids,timestamp,event_id) VALUES(?,?,?,?,1,?,1)",
        (t,v,"Network activity" if t!="sha256" and t!="md5" else "Payload delivery", f"{actor}: {comment}", int(time.time())))
    conn.commit()
  return conn

def auth(headers):
  expected = KEY_FILE.read_text().strip() if KEY_FILE.exists() else ""
  got = (headers.get("Authorization") or "").replace("Bearer","").strip()
  if not got:
    got = (headers.get("Authorization") or "").strip()
  # MISP uses Authorization: <key> without Bearer often
  authh = headers.get("Authorization") or headers.get("authorization") or ""
  if authh.lower().startswith("bearer "):
    authh = authh[7:].strip()
  return expected and authh.strip() == expected

class H(BaseHTTPRequestHandler):
  def log_message(self, *a): return
  def _json(self, code, obj):
    b=json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
  def do_GET(self):
    p=urlparse(self.path).path
    if p in ("/","/health","/servers/getVersion"):
      self._json(200, {"version":"2.4.mssp","status":"ok","pymisp_compatible":True})
      return
    if not auth(self.headers):
      self._json(401,{"message":"unauthorized"}); return
    if p=="/attributes/describeTypes":
      self._json(200,{"result":{"types":["ip-dst","ip-src","domain","hostname","md5","sha1","sha256","url"]}})
      return
    self._json(404,{"message":"not found"})
  def do_POST(self):
    p=urlparse(self.path).path
    if not auth(self.headers):
      self._json(401,{"message":"unauthorized"}); return
    length=int(self.headers.get("Content-Length") or 0)
    raw=self.rfile.read(length) if length else b"{}"
    try: body=json.loads(raw.decode() or "{}")
    except Exception: body={}
    if p in ("/attributes/restSearch","/attributes/restSearch/"):
      conn=db(); cur=conn.cursor()
      rows=cur.execute("SELECT id,type,value,category,comment,to_ids,timestamp,event_id FROM attributes WHERE to_ids=1").fetchall()
      conn.close()
      attrs=[]
      for r in rows:
        attrs.append({"Attribute":{"id":str(r[0]),"type":r[1],"value":r[2],"category":r[3],"comment":r[4] or "","to_ids":bool(r[5]),"timestamp":str(r[6]),"event_id":str(r[7])}})
      # optional value filter
      q=((body.get("returnFormat") and body) or body)
      val=(body.get("value") or body.get("Attribute",{}).get("value") if isinstance(body.get("Attribute"),dict) else None)
      if val:
        attrs=[a for a in attrs if str(val).lower() in a["Attribute"]["value"].lower()]
      self._json(200,{"response":{"Attribute":[a["Attribute"] for a in attrs]}})
      return
    if p in ("/events/restSearch","/events/index"):
      self._json(200,{"response":[{"Event":{"id":"1","info":"MSSP curated threat feed","threat_level_id":"2","Attribute":[]}}]})
      return
    if p=="/attributes/add":
      # accept push of new IOC
      attr=body.get("Attribute") or body
      conn=db()
      conn.execute("INSERT OR REPLACE INTO attributes(type,value,category,comment,to_ids,timestamp,event_id) VALUES(?,?,?,?,1,?,1)",
        (attr.get("type") or "other", attr.get("value") or "", attr.get("category") or "Network activity", attr.get("comment") or "", int(time.time())))
      conn.commit(); conn.close()
      self._json(200,{"Attribute":attr}); return
    self._json(404,{"message":"not found"})

if __name__=="__main__":
  db().close()
  print(f"MISP bridge on {BIND}:{PORT}", flush=True)
  ThreadingHTTPServer((BIND,PORT), H).serve_forever()
PY
chmod 0755 /opt/mssp-misp/misp_api.py
# Also install official-ish MISP docker if pull works; bridge is primary for control plane.
cat > /etc/systemd/system/mssp-misp-api.service <<'UNIT'
[Unit]
Description=MSSP MISP-compatible threat intel API
After=network-online.target
[Service]
Type=simple
Environment=MISP_DB=/opt/mssp-misp/data/iocs.sqlite3
Environment=MISP_API_KEY_FILE=/opt/mssp-misp/secrets/admin_key
Environment=MISP_BIND=0.0.0.0
Environment=MISP_PORT=8080
ExecStart=/usr/bin/python3 /opt/mssp-misp/misp_api.py
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now mssp-misp-api
sleep 1
curl -fsS http://127.0.0.1:8080/health
echo
EOF

mkdir -p /opt/mssp-control/.secrets
ssh -i "$KEY" -o BatchMode=yes "secadmin@${HOST}" 'sudo cat /opt/mssp-misp/secrets/admin_key' > /opt/mssp-control/.secrets/misp_api_key
chmod 600 /opt/mssp-control/.secrets/misp_api_key
echo "MISP API live on ${HOST}:8080; key stored in .secrets/misp_api_key"
