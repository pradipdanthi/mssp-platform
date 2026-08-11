#!/usr/bin/env bash
# Download ALL appliance catalogue engine artifacts into iso/offline-packages/
# for airgap firstboot: .debs + static binaries (nuclei/vuls) + python wheels.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${KEVANTIC_OFFLINE_PACKAGES:-$ROOT/iso/offline-packages}"
BIN_OUT="$OUT/bin"
WHEEL_OUT="$OUT/wheels"
MANIFEST="$OUT/MANIFEST.txt"
IMAGE="${KEVANTIC_OFFLINE_FETCH_IMAGE:-ubuntu:24.04}"
WAZUH_PKG_VER="${KEVANTIC_WAZUH_MANAGER_DEB_VERSION:-4.14.6-1}"
NUCLEI_VER="${KEVANTIC_NUCLEI_VERSION:-3.11.0}"
VULS_VER="${KEVANTIC_VULS_VERSION:-0.40.1}"
ZEEK_VER="${KEVANTIC_ZEEK_DEB_VERSION:-8.0.9-0}"
ZEEK_BASE="https://download.opensuse.org/repositories/security:/zeek/xUbuntu_24.04/amd64"

mkdir -p "$OUT" "$BIN_OUT" "$WHEEL_OUT"
find "$OUT" -maxdepth 1 -type f -name '*.deb' -delete
rm -f "$OUT/SHA256SUMS" "$MANIFEST"
rm -rf "$BIN_OUT"/* "$WHEEL_OUT"/*

echo "=== 1/4 APT engine packages (wazuh, fluent-bit, suricata, crypto, podman) ==="
docker run --rm \
  -e DEBIAN_FRONTEND=noninteractive \
  -e WAZUH_PKG_VER="$WAZUH_PKG_VER" \
  -v "$OUT:/out" \
  "$IMAGE" \
  bash -c '
set -euo pipefail
apt-get update -qq
apt-get install -y -qq curl gnupg apt-transport-https ca-certificates >/dev/null
mkdir -p /tmp/debs
cleanup() { rm -f /var/cache/apt/archives/*.deb; }

# Suricata + deps
cleanup
apt-get install -y -qq --download-only suricata
cp -a /var/cache/apt/archives/*.deb /tmp/debs/

# python3-cryptography + pip/venv (license + engine)
cleanup
apt-get install -y -qq --download-only python3-cryptography python3-pip python3-venv
cp -a /var/cache/apt/archives/*.deb /tmp/debs/

# podman (container runtime for future engine containers)
cleanup
apt-get install -y -qq --download-only podman
cp -a /var/cache/apt/archives/*.deb /tmp/debs/ || true

# Wazuh Manager
curl -fsSL https://packages.wazuh.com/key/GPG-KEY-WAZUH | gpg --dearmor -o /usr/share/keyrings/wazuh.gpg
echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" \
  > /etc/apt/sources.list.d/wazuh.list
apt-get update -qq
cleanup
apt-get install -y -qq --download-only "wazuh-manager=${WAZUH_PKG_VER}" \
  || apt-get install -y -qq --download-only wazuh-manager
cp -a /var/cache/apt/archives/wazuh*.deb /tmp/debs/

# Fluent Bit
curl -fsSL https://packages.fluentbit.io/fluentbit.key | gpg --dearmor -o /usr/share/keyrings/fluentbit.gpg
echo "deb [signed-by=/usr/share/keyrings/fluentbit.gpg] https://packages.fluentbit.io/ubuntu/noble noble main" \
  > /etc/apt/sources.list.d/fluent-bit.list
apt-get update -qq
cleanup
apt-get install -y -qq --download-only fluent-bit
cp -a /var/cache/apt/archives/fluent*.deb /tmp/debs/

cp -a /tmp/debs/*.deb /out/
chmod a+r /out/*.deb
'

echo "=== 2/4 Zeek LTS debs (openSUSE OBS) ==="
for pkg in \
  "zeek-lts-core_${ZEEK_VER}_amd64.deb" \
  "zeek-lts_${ZEEK_VER}_amd64.deb" \
  "zeekctl-lts_${ZEEK_VER}_amd64.deb" \
  "libbroker-lts-dev_${ZEEK_VER}_amd64.deb"
do
  url="$ZEEK_BASE/$pkg"
  echo "  GET $pkg"
  if ! curl -fsSL --max-time 180 -o "$OUT/$pkg" "$url"; then
    echo "WARN: skip $pkg (not found)" >&2
    rm -f "$OUT/$pkg"
  fi
done
# Prefer runtime libbroker if separate package exists
curl -fsSL --max-time 180 -o "$OUT/libbroker-tmp.deb" \
  "$ZEEK_BASE/libbroker-8.0-dev_8.0.9-0_amd64.deb" 2>/dev/null \
  && mv -f "$OUT/libbroker-tmp.deb" "$OUT/libbroker-8.0-dev_8.0.9-0_amd64.deb" \
  || rm -f "$OUT/libbroker-tmp.deb"

echo "=== 3/4 Nuclei + Vuls static binaries ==="
tmpdir=$(mktemp -d)
curl -fsSL --max-time 180 -o "$tmpdir/nuclei.zip" \
  "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VER}/nuclei_${NUCLEI_VER}_linux_amd64.zip"
python3 - <<PY
import zipfile, os, shutil, stat
from pathlib import Path
z=zipfile.ZipFile("$tmpdir/nuclei.zip")
dest=Path("$tmpdir/nuclei_out"); dest.mkdir(parents=True, exist_ok=True)
z.extractall(dest)
# prefer file named exactly nuclei
cands=list(dest.rglob("nuclei"))
files=[p for p in cands if p.is_file()]
if not files:
    raise SystemExit("nuclei binary not found in zip")
src=files[0]
out=Path("$BIN_OUT/nuclei")
shutil.copy2(src, out)
out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print("installed", out, "from", src, "size", out.stat().st_size)
PY
[[ -f "$BIN_OUT/nuclei" ]] || { echo "FAIL: nuclei binary missing" >&2; exit 3; }

curl -fsSL --max-time 180 -o "$tmpdir/vuls.tgz" \
  "https://github.com/future-architect/vuls/releases/download/v${VULS_VER}/vuls_${VULS_VER}_linux_amd64.tar.gz"
mkdir -p "$tmpdir/vuls_out"
tar -xzf "$tmpdir/vuls.tgz" -C "$tmpdir/vuls_out"
python3 - <<PY
import shutil, stat
from pathlib import Path
files=[p for p in Path("$tmpdir/vuls_out").rglob("vuls") if p.is_file()]
if not files:
    raise SystemExit("vuls binary not found")
out=Path("$BIN_OUT/vuls")
shutil.copy2(files[0], out)
out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print("installed", out, "size", out.stat().st_size)
PY
[[ -f "$BIN_OUT/vuls" ]] || { echo "FAIL: vuls binary missing" >&2; exit 3; }

curl -fsSL --max-time 180 -o "$tmpdir/vuls-scanner.tgz" \
  "https://github.com/future-architect/vuls/releases/download/v${VULS_VER}/vuls-scanner_${VULS_VER}_linux_amd64.tar.gz" || true
if [[ -f "$tmpdir/vuls-scanner.tgz" ]]; then
  mkdir -p "$tmpdir/vs"
  tar -xzf "$tmpdir/vuls-scanner.tgz" -C "$tmpdir/vs"
  python3 - <<PY
import shutil, stat
from pathlib import Path
files=[p for p in Path("$tmpdir/vs").rglob("vuls-scanner") if p.is_file()]
if files:
    out=Path("$BIN_OUT/vuls-scanner")
    shutil.copy2(files[0], out)
    out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("installed", out)
PY
fi
rm -rf "$tmpdir"

echo "=== 4/4 DuckDB wheel (offline pip) ==="
docker run --rm \
  -v "$WHEEL_OUT:/wheels" \
  "$IMAGE" \
  bash -c '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-pip >/dev/null
pip3 download --dest /wheels "duckdb>=1.1.0,<2" 2>/dev/null \
  || pip3 download --dest /wheels duckdb
chmod a+r /wheels/*
'

echo "=== Verify required artifacts ==="
fail=0
for pat in wazuh-manager fluent-bit suricata python3-cryptography; do
  if ls "$OUT"/${pat}*.deb >/dev/null 2>&1 || ls "$OUT"/*${pat}*.deb >/dev/null 2>&1; then
    echo "OK deb: $pat"
  else
    echo "FAIL deb: $pat" >&2
    fail=1
  fi
done
# zeek — at least core
if ls "$OUT"/zeek-lts*.deb >/dev/null 2>&1 || ls "$OUT"/zeek*.deb >/dev/null 2>&1; then
  echo "OK deb: zeek"
else
  echo "FAIL deb: zeek" >&2
  fail=1
fi
for b in nuclei vuls; do
  if [[ -x "$BIN_OUT/$b" ]]; then echo "OK bin: $b"; else echo "FAIL bin: $b" >&2; fail=1; fi
done
if ls "$WHEEL_OUT"/duckdb*.whl >/dev/null 2>&1; then echo "OK wheel: duckdb"; else echo "FAIL wheel: duckdb" >&2; fail=1; fi
[[ "$fail" == "0" ]] || exit 3

(
  cd "$OUT"
  {
    echo "# Kevantic appliance offline catalogue engines"
    echo "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "# wazuh=$WAZUH_PKG_VER nuclei=$NUCLEI_VER vuls=$VULS_VER zeek=$ZEEK_VER"
    echo "## debs"
    ls -1 *.deb 2>/dev/null | sort
    echo "## bin"
    ls -1 bin 2>/dev/null || true
    echo "## wheels"
    ls -1 wheels 2>/dev/null || true
  } > "$MANIFEST"
  find . -type f \( -name '*.deb' -o -name 'nuclei' -o -name 'vuls*' -o -name '*.whl' \) -print0 \
    | sort -z | xargs -0 sha256sum > SHA256SUMS
)

echo "Offline pool size: $(du -sh "$OUT" | awk '{print $1}')"
echo "Deb count: $(find "$OUT" -maxdepth 1 -name '*.deb' | wc -l)"
echo "B2_OFFLINE_PACKAGES_OK path=$OUT"
