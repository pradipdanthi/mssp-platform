#!/usr/bin/env bash
# Wrapper: sync MSSP EDR active-response scripts from control-plane deploy/ to an appliance.
# Delegates to kevantic-appliance/scripts/sync_appliance_edr_ar_scripts.sh
set -euo pipefail
BUILDER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTRL="$(cd "$BUILDER_ROOT/.." && pwd)"
exec "$CTRL/kevantic-appliance/scripts/sync_appliance_edr_ar_scripts.sh" "$@"
