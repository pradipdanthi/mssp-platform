#!/usr/bin/env bash
# MSSP Linux mid-layer execve telemetry (auditd → Wazuh localfile).
# Idempotent. Fail-open: never undo a successful wazuh-agent enrollment.
# Output is native audit.log (Wazuh log_format=audit) so Manager alerts carry
# data.audit.{pid,ppid,exe,comm,uid,auid,cwd,command,execve.a*} which
# edr_process_tree.normalize_process_event maps to raw_source=endpoint_audit_exec.
set +e
umask 022

echo "[MSSP-TELEMETRY] Installing auditd execve collector..."

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
rules_src=""
if [[ -n "${script_dir}" && -f "${script_dir}/mssp-exec.rules" ]]; then
  rules_src="${script_dir}/mssp-exec.rules"
fi

already_rules=0
already_localfile=0
[[ -f /etc/audit/rules.d/mssp-exec.rules ]] && already_rules=1
if [[ -f /var/ossec/etc/ossec.conf ]] && grep -q '/var/log/audit/audit.log' /var/ossec/etc/ossec.conf; then
  already_localfile=1
fi
if [[ "${already_rules}" -eq 1 && "${already_localfile}" -eq 1 ]]; then
  echo "[MSSP-TELEMETRY] already configured"
  echo "[MSSP-TELEMETRY] MSSP_LINUX_TELEMETRY_OK"
  exit 0
fi

if ! command -v auditctl >/dev/null 2>&1 && ! command -v auditd >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y auditd audispd-plugins >/dev/null 2>&1
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y audit audit-libs >/dev/null 2>&1
  elif command -v yum >/dev/null 2>&1; then
    yum install -y audit audit-libs >/dev/null 2>&1
  else
    echo "[MSSP-TELEMETRY] WARN: no package manager for auditd" >&2
    exit 1
  fi
fi

mkdir -p /etc/audit/rules.d
if [[ -n "${rules_src}" ]]; then
  cp -f "${rules_src}" /etc/audit/rules.d/mssp-exec.rules
else
  cat > /etc/audit/rules.d/mssp-exec.rules <<'RULES'
## MSSP Linux execve collection (collect != alert)
## Captures pid, ppid, comm, exe, uid/auid, cwd, command line (EXECVE a0..).
-a always,exit -F arch=b64 -S execve,execveat -F key=mssp_exec
-a always,exit -F arch=b32 -S execve,execveat -F key=mssp_exec
RULES
fi
chmod 0640 /etc/audit/rules.d/mssp-exec.rules

if command -v augenrules >/dev/null 2>&1; then
  augenrules --load >/dev/null 2>&1
fi
systemctl enable auditd >/dev/null 2>&1
systemctl restart auditd >/dev/null 2>&1 || service auditd restart >/dev/null 2>&1

conf="/var/ossec/etc/ossec.conf"
if [[ ! -f "${conf}" ]]; then
  echo "[MSSP-TELEMETRY] WARN: ossec.conf missing; enroll agent then re-run" >&2
  exit 1
fi

if grep -q 'MSSP Linux execve telemetry' "${conf}" || grep -q '/var/log/audit/audit.log' "${conf}"; then
  echo "[MSSP-TELEMETRY] Wazuh audit localfile already present"
else
  python3 - "${conf}" <<'PY'
import sys
from pathlib import Path
conf = Path(sys.argv[1])
text = conf.read_text(encoding="utf-8")
marker = "</ossec_config>"
idx = text.rfind(marker)
if idx < 0:
    raise SystemExit("ossec.conf missing </ossec_config>")
block = """
  <!-- BEGIN MSSP Linux execve telemetry -->
  <localfile>
    <log_format>audit</log_format>
    <location>/var/log/audit/audit.log</location>
  </localfile>
  <!-- END MSSP Linux execve telemetry -->
"""
conf.write_text(text[:idx] + block + "\n" + text[idx:], encoding="utf-8")
print("ossec.conf audit localfile added")
PY
  if [[ $? -ne 0 ]]; then
    tmp="${conf}.mssp-linux-exec.new"
    awk '
      /<\/ossec_config>/ && !done {
        print "  <!-- BEGIN MSSP Linux execve telemetry -->"
        print "  <localfile>"
        print "    <log_format>audit</log_format>"
        print "    <location>/var/log/audit/audit.log</location>"
        print "  </localfile>"
        print "  <!-- END MSSP Linux execve telemetry -->"
        done=1
      }
      { print }
    ' "${conf}" > "${tmp}" && mv -f "${tmp}" "${conf}"
  fi
fi

systemctl restart wazuh-agent >/dev/null 2>&1
echo "[MSSP-TELEMETRY] MSSP_LINUX_TELEMETRY_OK"
exit 0
