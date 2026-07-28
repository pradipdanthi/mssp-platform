#!/usr/bin/env bash
# KB-078: Live install Nuclei + Vuls free stack.
# Target: VM 109 (greenbone) at /opt/mssp-vuln-free — NOT the control plane.
# Run via: ssh greenbone 'sudo bash -s' < this script
# Or copy to host and: sudo VULN_FREE_ROOT=/opt/mssp-vuln-free ./kb078_install_vuln_free_stack.sh
# No secrets. Safe to re-run: skips when install marker exists unless FORCE=1.
set -euo pipefail

ROOT="${VULN_FREE_ROOT:-/opt/mssp-vuln-free}"
STATE="${VULN_FREE_STATE:-/var/lib/mssp/vuln-free}"
MARKER="${STATE}/installed"
NUCLEI_VERSION="${NUCLEI_VERSION:-3.11.0}"
ARCH="${NUCLEI_ARCH:-linux_amd64}"
ZIP="nuclei_${NUCLEI_VERSION}_${ARCH}.zip"
URL="https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/${ZIP}"
FETCH_DBS="${FETCH_VULN_DBS:-1}"
LINK_SYSTEM_BIN="${LINK_SYSTEM_BIN:-1}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root via sudo on VM 109 (secadmin SSH + sudo). Root SSH login is not required." >&2
  echo "  Example: ssh greenbone 'sudo bash -s' < scripts/kb078_install_vuln_free_stack.sh" >&2
  exit 1
fi

echo "======================================================================"
echo "KB-078: Install Nuclei + Vuls free stack → ${ROOT}"
echo "======================================================================"

if [[ -f "${MARKER}" && "${FORCE:-0}" != "1" ]]; then
  echo "Install marker already present: ${MARKER}"
  echo "Set FORCE=1 to reinstall. Exiting."
  exit 0
fi

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl unzip jq >/dev/null

command -v docker >/dev/null || { echo "Docker required" >&2; exit 1; }

mkdir -p \
  "${ROOT}/bin" \
  "${ROOT}/nuclei-templates" \
  "${ROOT}/vuls/results" \
  "${ROOT}/vuls/logs" \
  "${STATE}"
chmod 0750 "${ROOT}" "${STATE}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "→ Downloading Nuclei v${NUCLEI_VERSION}..."
curl -fsSL -o "${TMP}/${ZIP}" "${URL}"
unzip -o -q "${TMP}/${ZIP}" -d "${TMP}"
install -m 0755 "${TMP}/nuclei" "${ROOT}/bin/nuclei"
if [[ "${LINK_SYSTEM_BIN}" == "1" ]]; then
  ln -sfn "${ROOT}/bin/nuclei" /usr/local/bin/nuclei
fi

echo "→ Updating Nuclei templates..."
"${ROOT}/bin/nuclei" -update-templates -ud "${ROOT}/nuclei-templates" || true
"${ROOT}/bin/nuclei" -version

echo "→ Pulling Vuls Docker images..."
for img in \
  vuls/vuls:latest \
  vuls/go-cve-dictionary:latest \
  vuls/goval-dictionary:latest \
  vuls/gost:latest \
  vuls/go-kev:latest
do
  docker pull "${img}"
done

CONFIG="${ROOT}/vuls/config.toml"
if [[ ! -f "${CONFIG}" ]]; then
  cat > "${CONFIG}" <<EOF
# Host-local Vuls config stub — no secrets in Git.
# Add scan targets only with written customer scope approval.

[cveDict]
type = "sqlite3"
SQLite3Path = "${ROOT}/vuls/cve.sqlite3"

[ovalDict]
type = "sqlite3"
SQLite3Path = "${ROOT}/vuls/oval.sqlite3"

[gost]
type = "sqlite3"
SQLite3Path = "${ROOT}/vuls/gost.sqlite3"

[kevuln]
type = "sqlite3"
SQLite3Path = "${ROOT}/vuls/go-kev.sqlite3"

[servers]
EOF
  chmod 0640 "${CONFIG}"
fi

if [[ "${FETCH_DBS}" == "1" ]]; then
  echo "→ Fetching Vuls vulnerability databases (this can take a long time)..."
  docker run --rm \
    -v "${ROOT}/vuls:/go-cve-dictionary" \
    -v "${ROOT}/vuls/logs:/var/log/go-cve-dictionary" \
    vuls/go-cve-dictionary:latest fetch nvd

  docker run --rm \
    -v "${ROOT}/vuls:/goval-dictionary" \
    -v "${ROOT}/vuls/logs:/var/log/goval-dictionary" \
    vuls/goval-dictionary:latest fetch ubuntu 20.04 22.04 24.04

  docker run --rm \
    -v "${ROOT}/vuls:/gost" \
    -v "${ROOT}/vuls/logs:/var/log/gost" \
    vuls/gost:latest fetch ubuntu

  docker run --rm \
    -v "${ROOT}/vuls:/go-kev" \
    -v "${ROOT}/vuls/logs:/var/log/go-kev" \
    vuls/go-kev:latest fetch kevuln
else
  echo "→ Skipping DB fetch (FETCH_VULN_DBS=0)"
fi

cat > "${MARKER}" <<EOF
installed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
nuclei_version=${NUCLEI_VERSION}
host=$(hostname)
kb=078
path=${ROOT}
vm=109
EOF
chmod 0640 "${MARKER}"

echo
echo "======================================================================"
echo "KB-078 INSTALL COMPLETE"
echo "  Host: VM 109 (greenbone) — scanners stay off the control plane"
echo "  Nuclei: ${ROOT}/bin/nuclei"
echo "  Templates: ${ROOT}/nuclei-templates"
echo "  Vuls workdir: ${ROOT}/vuls"
echo "  Marker: ${MARKER}"
echo "======================================================================"
