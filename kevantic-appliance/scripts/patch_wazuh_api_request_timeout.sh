#!/usr/bin/env bash
# Raise Wazuh API intervals.request_timeout (default 10s) so isolate/unisolate AR
# scripts can finish on Windows agents before the Manager API returns 500/3021.
set -euo pipefail

API="/var/ossec/api/configuration/api.yaml"
TIMEOUT="${1:-120}"

[[ -f "$API" ]] || { echo "missing $API" >&2; exit 1; }

python3 - "$API" "$TIMEOUT" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
timeout = sys.argv[2]
text = path.read_text(encoding="utf-8")
block = f"intervals:\n   request_timeout: {timeout}\n"
if re.search(r"^intervals:\s*$", text, re.M):
    text = re.sub(
        r"(?m)^intervals:\s*\n(?:#?\s*request_timeout:.*\n)?",
        block,
        text,
        count=1,
    )
elif re.search(r"^# intervals:\s*$", text, re.M):
    text = text.replace(
        "# intervals:\n#   request_timeout: 10\n",
        block,
        1,
    )
else:
    text = text.rstrip() + "\n\n" + block
path.write_text(text, encoding="utf-8")
print(f"OK: intervals.request_timeout={timeout} in {path}")
PY

systemctl restart wazuh-manager 2>/dev/null || /var/ossec/bin/wazuh-control restart
echo "Wazuh manager restarted"
