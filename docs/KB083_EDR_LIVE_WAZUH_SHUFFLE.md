# KB-083 — Live Shuffle forensics + Wazuh Active Response wiring

Status: **Live verified on control plane + Wazuh manager/agent lab** (2026-07-28).

## What was wired

### Shuffle forensics
- Control plane posts to existing Shuffle webhook (`.secrets/shuffle_webhook_url`).
- Payload includes `action`, `workflow` (`EDR_SHUFFLE_FORENSICS_WORKFLOW`, default `EDR_COLLECT_FORENSICS`), `agent_id`, `tenant_short_code`, `mode`.
- **Verified:** HTTP 200 from Shuffle for `COLLECT_FORENSICS` (API + direct client).

### Wazuh Active Response (Linux agent `001` / `linux-endpoint-lab`)
Custom AR scripts on manager + agent:

| Command | Executable | Effect |
|---------|------------|--------|
| `mssp-isolate-host` | Python AR | Temporary OUTPUT quarantine (allow manager + DNS); auto-release |
| `mssp-kill-process` | Python AR | `SIGKILL` target PID |
| `mssp-block-hash` | Python AR | Append SHA256 to `/var/ossec/etc/mssp_blocked_hashes.txt` |

API format (Wazuh 4.14): `PUT /active-response?agents_list=<id>` with `{"command":"!mssp-…","arguments":[...]}`.

**Verified live:**
- Isolate creates `iptables` chain `MSSP_ISOLATE`
- Kill terminates lab `sleep` processes (may queue behind prior AR)
- Block-hash updates denylist file
- Control-plane `POST /v1/edr/actions/execute` as `customer_admin` returns `executed` for forensics / kill / isolate

## Ops notes
1. Isolate keeps manager (`192.168.0.211`) reachable; default duration `EDR_ISOLATE_SECONDS` (120).
2. While a host is isolated, further AR may queue until the agent/manager session recovers — prefer kill **before** isolate in playbooks.
3. Windows agent (`003`) is still `pending` — Linux AR only for now.
4. Shuffle workflow should branch on `action` / `workflow` fields for offline collector; Velociraptor server path activates when `VELOCIRAPTOR_SERVER_URL` is set.

## Deploy helpers
- Scripts: `deploy/wazuh-active-response/mssp-*`
- Installer: `scripts/kb083_deploy_wazuh_edr_ar.sh`
