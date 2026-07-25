#!/usr/bin/env bash
# KB-049 helper: configure Wazuh Manager to forward alerts to a Shuffle webhook.
# Usage (on VM 100 or from automation after you paste the webhook URL):
#   export SHUFFLE_WEBHOOK_URL='http://192.168.0.212:3001/api/v1/hooks/webhook_<ID>'
#   export WAZUH_LEVEL_MIN=10
#   ./scripts/kb049_configure_wazuh_shuffle_integration.sh
#
# Secrets: webhook URL is runtime-only — never commit it.
set -euo pipefail

if [[ -z "${SHUFFLE_WEBHOOK_URL:-}" ]]; then
  echo "Set SHUFFLE_WEBHOOK_URL to your Shuffle webhook URI first." >&2
  exit 1
fi

LEVEL_MIN="${WAZUH_LEVEL_MIN:-10}"
REMOTE_HOST="${WAZUH_SSH_HOST:-wazuh-stack}"
MARKER_BEGIN="<!-- BEGIN MSSP KB-049 Shuffle integration -->"
MARKER_END="<!-- END MSSP KB-049 Shuffle integration -->"

ssh -o BatchMode=yes "$REMOTE_HOST" "sudo python3 -" <<PY
from pathlib import Path
import re
path = Path("/var/ossec/etc/ossec.conf")
text = path.read_text()
block = '''${MARKER_BEGIN}
  <integration>
    <name>shuffle</name>
    <hook_url>${SHUFFLE_WEBHOOK_URL}</hook_url>
    <level>${LEVEL_MIN}</level>
    <alert_format>json</alert_format>
  </integration>
${MARKER_END}
'''
if "${MARKER_BEGIN}" in text:
    text = re.sub(
        re.escape("${MARKER_BEGIN}") + r".*?" + re.escape("${MARKER_END}"),
        block.strip(),
        text,
        flags=re.S,
    )
else:
    if "</ossec_config>" not in text:
        raise SystemExit("ossec.conf missing </ossec_config>")
    text = text.replace("</ossec_config>", block + "\n</ossec_config>", 1)
path.write_text(text)
print("Wrote Shuffle integration to ossec.conf (level>=${LEVEL_MIN})")
PY

ssh -o BatchMode=yes "$REMOTE_HOST" 'sudo /var/ossec/bin/wazuh-control restart'
echo "Wazuh manager restart requested. Verify integrations.log on VM 101."
