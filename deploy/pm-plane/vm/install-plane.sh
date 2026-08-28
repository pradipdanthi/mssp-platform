#!/usr/bin/env bash
# Install Plane Community Edition via official setup.sh (non-interactive install + start).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${HOME}/plane-install"
PLANE_APP="${HOME}/plane-app"
SETUP_SH="${INSTALL_ROOT}/setup.sh"
ENV_TEMPLATE="${SCRIPT_DIR}/plane.env.kevantic"

mkdir -p "${INSTALL_ROOT}"
cd "${INSTALL_ROOT}"

if [[ ! -f "${SETUP_SH}" ]]; then
  echo "Downloading Plane setup.sh..."
  curl -fsSL -o setup.sh https://github.com/makeplane/plane/releases/latest/download/setup.sh
  chmod +x setup.sh
fi

# Official installer is menu-driven; feed options: 1=Install x86_64, then 2=Start, 8=Exit
if [[ ! -d "${PLANE_APP}" ]]; then
  echo "Installing Plane files (option 1)..."
  printf '1\n8\n' | "${SETUP_SH}" || true
fi

if [[ ! -f "${PLANE_APP}/plane.env" ]]; then
  echo "plane-app not found after install. Check ${INSTALL_ROOT} logs."
  exit 1
fi

if [[ -f "${ENV_TEMPLATE}" ]]; then
  echo "Applying Kevantic plane.env template..."
  cp "${ENV_TEMPLATE}" "${PLANE_APP}/plane.env"
fi

# Detect VM IP for optional LAN access (NAT default uses localhost:8080 on host)
VM_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -n "${VM_IP}" ]]; then
  echo "VM IP: ${VM_IP} (use http://localhost:8080 from laptop via port forward)"
fi

echo "Starting Plane (option 2)..."
printf '2\n8\n' | "${SETUP_SH}"

ln -sf "${SETUP_SH}" "${HOME}/plane-setup.sh"

echo ""
echo "================================================================"
echo "Plane should be running."
echo "  From Windows laptop browser: http://localhost:8080"
echo "  Manage: ~/plane-setup.sh  (2=start, 3=stop, 5=upgrade, 7=backup)"
echo "  Config: ~/plane-app/plane.env"
echo "  Next: see deploy/pm-plane/docs/KEVANTIC_PM_BOOTSTRAP.md"
echo "================================================================"

# Wait for API health (best effort)
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1/api/instances/" >/dev/null 2>&1; then
    echo "Plane API is up."
    exit 0
  fi
  sleep 5
done
echo "Plane may still be starting. Check: cd ~/plane-app && docker compose ps"
