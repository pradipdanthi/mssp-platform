#!/usr/bin/env bash
# Install `custom-mssp-ingress`: Wazuh's stock shuffle integration, but with the
# webhook token redacted from integrations.log. Stock shuffle.py writes its full
# argv (including hook_url, which carries the ingress token in its path) on every
# call. Custom integrations survive Wazuh upgrades; the stock file does not.
#
# Run on the Wazuh Manager as root. Then set <name>custom-mssp-ingress</name> in
# the ossec.conf <integration> block and restart wazuh-manager.
set -euo pipefail

DIR=/var/ossec/integrations
SRC_PY="$DIR/shuffle.py"
DST=custom-mssp-ingress

[[ -f "$SRC_PY" && -f "$DIR/shuffle" ]] || { echo "stock shuffle integration missing" >&2; exit 1; }

install -o root -g wazuh -m 750 "$DIR/shuffle" "$DIR/$DST"

python3 - "$SRC_PY" "$DIR/$DST.py" <<'PY'
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()

needle = "args[1], args[2], args[3], "
if text.count(needle) != 1:
    sys.exit("unexpected shuffle.py layout: argv log line not found exactly once")
text = text.replace(needle, "args[1], args[2], _redact_hook(args[3]), ")

helper = (
    "\n\ndef _redact_hook(url: str) -> str:\n"
    "    \"\"\"MSSP: never write the ingress token (last path segment) to integrations.log.\"\"\"\n"
    "    return re.sub(r'(/hooks/[^/]+/)[^/?#]+', r'\\1<redacted>', url)\n"
    "\n\ndef _safe_exc(exc: BaseException) -> str:\n"
    "    return _redact_hook(str(exc))\n"
)
anchor = "\n\ndef main(args):"
if anchor not in text:
    sys.exit("unexpected shuffle.py layout: main() not found")
text = text.replace(anchor, helper + anchor, 1)
if not re.search(r"^import re$", text, re.M):
    text = text.replace("import sys", "import re\nimport sys", 1)

open(dst, "w", encoding="utf-8").write(text)
PY

chown root:wazuh "$DIR/$DST.py"
chmod 750 "$DIR/$DST.py"
echo "installed $DIR/$DST(.py)"
