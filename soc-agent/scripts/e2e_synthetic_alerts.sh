#!/usr/bin/env bash
set -euo pipefail
BASE="${SOC_AGENT_URL:-http://127.0.0.1:8088}"
TOKEN="${SOC_AGENT_INGEST_TOKEN:?set SOC_AGENT_INGEST_TOKEN}"

echo "=== health ==="
curl -fsS "$BASE/health"
echo

echo "=== Test A: benign brute-force (private IP) ==="
A=$(curl -fsS -X POST "$BASE/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Soc-Agent-Token: $TOKEN" \
  -d '{
    "title": "SSH brute force attempts from internal scanner",
    "severity": "medium",
    "description": "Multiple failed password authentication failures from lab jump host",
    "source_ip": "192.168.0.50",
    "destination_ip": "192.168.0.215",
    "tenant": "LAB",
    "tags": ["ssh", "brute"]
  }')
echo "$A" | python3 -m json.tool
echo "$A" | python3 -c 'import sys,json; r=json.load(sys.stdin); assert r["triage"]["classification"]=="benign", r; assert r["triage"]["disposition"]=="auto_close_benign", r; print("PASS A")'

echo "=== Test B: critical C2 / payload ==="
B=$(curl -fsS -X POST "$BASE/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Soc-Agent-Token: $TOKEN" \
  -d '{
    "title": "Suspicious C2 beacon with malware payload transfer",
    "severity": "critical",
    "description": "Host beacons to known command and control channel and downloads encrypted payload",
    "source_ip": "192.168.0.215",
    "destination_ip": "198.51.100.66",
    "domain": "evil-c2.example",
    "tenant": "LAB",
    "tags": ["c2", "malware"]
  }')
echo "$B" | python3 -m json.tool
echo "$B" | python3 -c 'import sys,json; r=json.load(sys.stdin); assert r["triage"]["disposition"]=="escalate", r; assert r["dossier_id"], r; assert any(m["technique_id"] in ("T1071","T1486") for m in r["enrichment"]["mitre"]), r; print("PASS B dossier", r["dossier_id"])'

echo "ALL E2E SYNTHETIC CHECKS PASSED"
