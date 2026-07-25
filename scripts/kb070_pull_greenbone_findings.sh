#!/usr/bin/env bash
# KB-070: Pull live Greenbone GMP findings (VM 109) → POST /integrations/vuln/sync.
# Secrets stay on hosts / gitignored files — never printed, never committed.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
GREENBONE_SSH_HOST="${GREENBONE_SSH_HOST:-greenbone}"
MAP_FILE="${GREENBONE_HOST_MAP_FILE:-$PROJECT_DIR/config/greenbone_host_tenant_map.yml}"
KEY_FILE="${VULN_SYNC_API_KEY_FILE:-$PROJECT_DIR/.secrets/vuln_sync_api_key}"
COMPOSE_FILE="${GREENBONE_COMPOSE_FILE:-/opt/mssp-greenbone/community/compose.yaml}"
COMPOSE_PROJECT="${GREENBONE_COMPOSE_PROJECT:-greenbone-community-edition}"
MIN_QOD="${GREENBONE_MIN_QOD:-70}"
LEVELS="${GREENBONE_LEVELS:-hml}"   # high/medium/low (omit log)
ROWS="${GREENBONE_RESULT_ROWS:-500}"
DRY_RUN="${DRY_RUN:-0}"

cd "$PROJECT_DIR"

fail() { echo "ERROR: $*" >&2; exit 1; }

[ -f "$MAP_FILE" ] || fail "mapping file missing: $MAP_FILE"
[ -f "$KEY_FILE" ] || fail "vuln sync key missing: $KEY_FILE (never commit)"
SYNC_KEY="$(tr -d '[:space:]' <"$KEY_FILE")"
[ -n "$SYNC_KEY" ] || fail "empty vuln sync key"

TMP_XML="$(mktemp)"
TMP_JSON="$(mktemp)"
trap 'rm -f "$TMP_XML" "$TMP_JSON"' EXIT

echo "KB-070: fetching Greenbone results via GMP (levels=$LEVELS min_qod=$MIN_QOD)..."

# Fetch results XML on VM 109 — password via mounted file only (never sudo argv).
ssh -o BatchMode=yes -o ConnectTimeout=15 "$GREENBONE_SSH_HOST" \
  "COMPOSE_FILE='$COMPOSE_FILE' COMPOSE_PROJECT='$COMPOSE_PROJECT' MIN_QOD='$MIN_QOD' LEVELS='$LEVELS' ROWS='$ROWS' bash -s" \
  >"$TMP_XML" <<'REMOTE'
set -euo pipefail
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
sudo awk -F= '/^GREENBONE_ADMIN_PASSWORD=/{print substr($0,index($0,"=")+1); exit}' \
  /opt/mssp-greenbone/admin.secret.env > "$WORKDIR/admin.password"
USER="$(sudo awk -F= '/^GREENBONE_ADMIN_USER=/{print substr($0,index($0,"=")+1); exit}' \
  /opt/mssp-greenbone/admin.secret.env || true)"
USER="${USER:-admin}"
printf '%s\n' "$USER" > "$WORKDIR/admin.user"
FILTER="apply_overrides=0 levels=${LEVELS} min_qod=${MIN_QOD} rows=${ROWS} first=1 sort-reverse=severity"
printf '%s\n' "$FILTER" > "$WORKDIR/filter.txt"
cat > "$WORKDIR/gmp_query.py" <<'PY'
from pathlib import Path
from gvm.connections import UnixSocketConnection
from gvm.protocols.gmp import Gmp
from gvm.transforms import EtreeCheckCommandTransform
from lxml import etree
user = Path("/run/mssp/admin.user").read_text().strip() or "admin"
password = Path("/run/mssp/admin.password").read_text().strip()
filter_term = Path("/run/mssp/filter.txt").read_text().strip()
with Gmp(connection=UnixSocketConnection(path="/run/gvmd/gvmd.sock", timeout=120),
         transform=EtreeCheckCommandTransform()) as gmp:
    gmp.authenticate(user, password)
    response = gmp.get_results(filter_string=filter_term, details=True)
    print(etree.tostring(response, encoding="unicode"))
PY
chmod 644 "$WORKDIR"/*
sudo docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" \
  run --rm --no-deps --user 1001 \
  -v "$WORKDIR/admin.password:/run/mssp/admin.password:ro" \
  -v "$WORKDIR/admin.user:/run/mssp/admin.user:ro" \
  -v "$WORKDIR/filter.txt:/run/mssp/filter.txt:ro" \
  -v "$WORKDIR/gmp_query.py:/run/mssp/gmp_query.py:ro" \
  --entrypoint python3 gvm-tools /run/mssp/gmp_query.py 2>/dev/null
REMOTE

python3 - "$TMP_XML" "$MAP_FILE" "$TMP_JSON" <<'PY'
import json, sys, re
from pathlib import Path
from xml.etree import ElementTree as ET

xml_path, map_path, out_path = sys.argv[1:4]
raw = Path(xml_path).read_text(encoding="utf-8", errors="replace").strip()
if not raw:
    raise SystemExit("empty GMP response")

root = ET.fromstring(raw)
status = root.get("status")
if status and status not in ("200", "201", "202"):
    raise SystemExit(f"GMP error status={status} text={root.get('status_text')}")

# Minimal YAML subset reader (no PyYAML dependency required).
def load_map(text: str) -> dict:
    default = "DEMO"
    hosts: dict = {}
    mode = None
    current = None
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("default_tenant_short_code:"):
            default = line.split(":", 1)[1].strip().strip("'\"")
            continue
        if line.startswith("hosts:"):
            mode = "hosts"
            continue
        if mode == "hosts":
            m = re.match(r'^  "([^"]+)":\s*$', line) or re.match(r"^  '([^']+)':\s*$", line) or re.match(r"^  ([^:#]+):\s*$", line)
            if m:
                current = m.group(1).strip()
                hosts[current] = {}
                continue
            if current and re.match(r"^    ", line):
                key, _, val = line.strip().partition(":")
                hosts[current][key.strip()] = val.strip().strip("'\"")
    return {"default_tenant_short_code": default, "hosts": hosts}

mapping = load_map(Path(map_path).read_text(encoding="utf-8"))
default_tenant = mapping["default_tenant_short_code"].upper()
host_map = mapping.get("hosts") or {}

def severity_of(result) -> str:
    threat = (result.findtext("threat") or "").strip().lower()
    try:
        score = float((result.findtext("severity") or "0").strip() or 0)
    except ValueError:
        score = 0.0
    if score >= 9.0 or threat == "critical":
        return "critical"
    if score >= 7.0 or threat == "high":
        return "high"
    if score >= 4.0 or threat == "medium":
        return "medium"
    if threat in ("low", "log", "false positive", "alarm"):
        # Keep low; skip pure log/false-positive noise below.
        if threat in ("log", "false positive"):
            return ""
        return "low"
    if score > 0:
        return "low"
    return ""


def first_cve(nvt) -> str | None:
    if nvt is None:
        return None
    direct = (nvt.findtext("cve") or "").strip()
    if direct and direct.upper() != "NOCVE":
        # May be comma-separated
        return direct.split(",")[0].strip()[:64]
    refs = nvt.find("refs")
    if refs is not None:
        for ref in refs.findall("ref"):
            if (ref.get("type") or "").lower() == "cve" and ref.get("id"):
                return ref.get("id").strip()[:64]
    return None


def host_key(result) -> str:
    host_el = result.find("host")
    if host_el is None:
        return ""
    # <host>192.168.0.215<asset asset_id="..."/></host> — text may include whitespace
    text = "".join(host_el.itertext()).strip()
    # Prefer leading IPv4
    m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
    if m:
        return m.group(1)
    return text.split()[0] if text else ""


batches: dict[str, list] = {}
skipped = 0
for result in root.findall("result"):
    rid = result.get("id") or ""
    if not rid:
        skipped += 1
        continue
    sev = severity_of(result)
    if not sev:
        skipped += 1
        continue
    nvt = result.find("nvt")
    title = (result.findtext("name") or (nvt.findtext("name") if nvt is not None else None) or "Greenbone finding").strip()
    title = title[:500]
    host = host_key(result)
    meta = host_map.get(host) or {}
    tenant = (meta.get("tenant_short_code") or default_tenant).upper()
    asset_hostname = meta.get("asset_hostname") or None
    desc = (result.findtext("description") or "").strip()
    summary = desc[:1200] if desc else f"Vulnerability finding on {host or 'unknown host'}."
    remediation = None
    # Prefer solution element when present
    sol = result.find("nvt/solution") if nvt is not None else None
    if sol is not None and (sol.text or "").strip():
        remediation = sol.text.strip()[:4000]
    elif desc:
        remediation = ("Review the finding and apply vendor updates where applicable.\n\n" + desc[:1500])[:4000]
    finding = {
        "external_finding_id": rid,
        "title": title,
        "severity": sev,
        "cve_id": first_cve(nvt),
        "nvt_oid": (nvt.get("oid") if nvt is not None else None),
        "asset_hostname": asset_hostname,
        "customer_safe_summary": summary[:5000],
        "remediation_summary": remediation,
        "create_recommendation": None,  # auto high/critical
        "recommendation_customer_visible": False,
    }
    batches.setdefault(tenant, []).append(finding)

payload = {
    "source_platform": "greenbone",
    "batches": [
        {"tenant_short_code": tenant, "findings": findings}
        for tenant, findings in sorted(batches.items())
    ],
    "stats": {
        "tenants": len(batches),
        "findings": sum(len(v) for v in batches.values()),
        "skipped": skipped,
    },
}
Path(out_path).write_text(json.dumps(payload), encoding="utf-8")
print(
    f"Parsed findings={payload['stats']['findings']} "
    f"tenants={payload['stats']['tenants']} skipped={skipped}"
)
PY

if [[ "$DRY_RUN" == "1" ]]; then
  python3 -m json.tool <"$TMP_JSON" | head -80
  echo "DRY_RUN=1 — not posting to control plane."
  exit 0
fi

python3 - "$TMP_JSON" "$CONTROL_PLANE_URL" "$SYNC_KEY" <<'PY'
import json, sys, urllib.error, urllib.request

path, base, key = sys.argv[1:4]
doc = json.loads(open(path, encoding="utf-8").read())
batches = doc.get("batches") or []
if not batches:
    print("No findings to sync (scan may still be running, or no high/medium/low results yet).")
    raise SystemExit(0)

total_ok = 0
for batch in batches:
    findings = batch["findings"]
    # Chunk to stay under API max_length=200
    for i in range(0, len(findings), 100):
        chunk = findings[i : i + 100]
        body = {
            "tenant_short_code": batch["tenant_short_code"],
            "source_platform": "greenbone",
            "findings": chunk,
        }
        req = urllib.request.Request(
            base.rstrip("/") + "/integrations/vuln/sync",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Vuln-Sync-Key": key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise SystemExit(f"sync HTTP {e.code} for {batch['tenant_short_code']}: {detail}") from None
        results = data.get("results") or []
        created = sum(1 for r in results if r.get("action") == "created")
        updated = sum(1 for r in results if r.get("action") == "updated")
        recs = sum(1 for r in results if r.get("recommendation_action") == "created")
        total_ok += len(results)
        print(
            f"tenant={data.get('short_code')} synced={len(results)} "
            f"created={created} updated={updated} recommendations_created={recs}"
        )

print(f"KB-070 pull complete — total synced rows: {total_ok}")
PY
