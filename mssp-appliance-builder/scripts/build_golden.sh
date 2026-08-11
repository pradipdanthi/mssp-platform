#!/usr/bin/env bash
# build_golden.sh — Start Proxmox-native Kevantic golden appliance Packer build.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="${HOME}/bin:${PATH}"

TOKEN_ENV="${ROOT}/.cache/proxmox-token.env"
[[ -f "$TOKEN_ENV" ]] || { echo "Missing $TOKEN_ENV — create Proxmox API token first" >&2; exit 2; }
set -a
# shellcheck disable=SC1090
source "$TOKEN_ENV"
set +a

command -v packer >/dev/null || { echo "packer not in PATH" >&2; exit 2; }

mkdir -p .cache output-mssp-appliance
chmod +x scripts/*.sh

echo "=== packer init ==="
packer init .

echo "=== NOTE: Subiquity ISO path often hangs on Proxmox (ens18 network loop). ==="
echo "=== Using cloud-image factory path (build_golden_cloudimg.sh) instead. ==="
chmod +x "${ROOT}/scripts/build_golden_cloudimg.sh" "${ROOT}/scripts/provision_via_vm112.sh"
"${ROOT}/scripts/build_golden_cloudimg.sh"
exit $?

echo "=== (legacy) packer validate ==="
BUILD_KEY=/opt/mssp-control/kevantic-appliance/.tools/build-ssh/kevantic_packer
PVE_KEY="${HOME}/.ssh/id_ed25519_proxmox"
REMOTE_HTTP='~/mssp-appliance-builder/http'
REMOTE_OUT='/tmp/mssp-appliance-cidata.iso'
ssh -i "$BUILD_KEY" -o BatchMode=yes -o IdentitiesOnly=yes kevantic@192.168.0.223 "mkdir -p ${REMOTE_HTTP}"
scp -o BatchMode=yes -i "$BUILD_KEY" "${ROOT}/http/user-data" "${ROOT}/http/meta-data" "kevantic@192.168.0.223:${REMOTE_HTTP}/"
ssh -i "$BUILD_KEY" -o BatchMode=yes -o IdentitiesOnly=yes kevantic@192.168.0.223 bash -s <<'EOF'
set -euo pipefail
OUT=/tmp/mssp-appliance-cidata.iso
HTTP="$HOME/mssp-appliance-builder/http"
rm -f "$OUT"
xorriso -as mkisofs -o "$OUT" -V cidata -r -J "$HTTP/meta-data" "$HTTP/user-data"
ls -lh "$OUT"
EOF
mkdir -p "${ROOT}/.cache"
scp -o BatchMode=yes -i "$BUILD_KEY" "kevantic@192.168.0.223:${REMOTE_OUT}" "${ROOT}/.cache/mssp-appliance-cidata.iso"
scp -o BatchMode=yes -i "$PVE_KEY" "${ROOT}/.cache/mssp-appliance-cidata.iso" "root@192.168.0.191:/var/lib/vz/template/iso/mssp-appliance-cidata.iso"
ssh -i "$PVE_KEY" -o BatchMode=yes root@192.168.0.191 'ls -lh /var/lib/vz/template/iso/mssp-appliance-cidata.iso'
echo CIDATA_READY

echo "=== packer validate ==="
packer validate -var-file=vars/lab.pkrvars.hcl .

echo "=== packer build (Proxmox VMID 199; Ansible via VM 112) ==="
echo "This typically takes 45–120+ minutes (Ubuntu install + offline engines)."
packer build -force -var-file=vars/lab.pkrvars.hcl . 2>&1 | tee .cache/packer-build.log
echo "BUILD_FINISHED rc=$?"
