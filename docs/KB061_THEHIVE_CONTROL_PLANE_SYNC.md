# KB-061 — TheHive to Control Plane Dashboard Sync

Status: **Implemented (lab)** — normalized SOC sync API + TheHive pull helper.  
Branch: `kb039-kb060-platform-roadmap-execution`

## Purpose

Close the product loop:

```text
Wazuh → Shuffle → TheHive  (KB-049)
                ↓
     POST /integrations/soc/sync  (this KB)
                ↓
 PostgreSQL security_alerts (+ incidents for high/critical)
                ↓
 Admin dashboard immediately; Customer portal only after SOC sets customer_visible
```

## Design decisions (lab v1)

| Decision | Choice |
|---|---|
| Ingress | Authenticated control-plane API (`X-SOC-Sync-Key`) |
| Tenant mapping | Default **DEMO** (`tenant_short_code`) |
| Objects created | Alert always; **incident** for high/critical |
| Customer visibility | Always `customer_visible = false` until Admin/SOC triage (KB-056) |
| Schema | No new tables; TheHive id stored in `external_alert_id` |
| Secrets | Gitignored `.secrets/soc_sync_api_key` mounted into backend — **never** commit keys |

## Customer safety

Customer portal must **never** receive raw TheHive JSON, observables, Shuffle logs, API keys, or internal notes. Sync stores only normalized title/description/severity summaries. Customer list/detail APIs still require `customer_visible = true`.

## Operator usage

### Sync key

Runtime file (gitignored): `/opt/mssp-control/.secrets/soc_sync_api_key`  
Mounted in `docker-compose.yml` as `SOC_SYNC_API_KEY_FILE=/run/secrets/soc_sync_api_key`.

### Pull existing TheHive alerts into DEMO

```bash
export THEHIVE_PASSWORD='<your TheHive password>'
./scripts/kb061_sync_thehive_alerts.sh
```

### Shuffle (optional next hop)

After TheHive create, add an HTTP request step to:

`POST http://192.168.0.201:8000/integrations/soc/sync`

Header: `X-SOC-Sync-Key: <runtime key>`  
Body: normalized JSON matching `SocSyncRequest` (no raw alert dump).

## Automatic sync (lab host)

On VM 100 (`mssp-control`), systemd runs the pull every **5 minutes**:

- timer: `mssp-kb061-thehive-sync.timer`
- service: `mssp-kb061-thehive-sync.service`

Check status:

```bash
systemctl status mssp-kb061-thehive-sync.timer --no-pager
journalctl -u mssp-kb061-thehive-sync.service -n 20 --no-pager
```

You do **not** need to run the sync script by hand for normal lab use.
Optional faster path: add Shuffle HTTP hop (see KB-062 helper) for near-instant sync after each TheHive create.

## Periodic sync (lab) (manual fallback)

`scripts/kb061_run_periodic_sync.sh` pulls TheHive alerts into DEMO every run.
Optional crontab (every 5 minutes):

```bash
*/5 * * * * /opt/mssp-control/scripts/kb061_run_periodic_sync.sh
```

If `crontab` is unavailable on the host, run the helper periodically by hand or with a supervised loop:

```bash
/opt/mssp-control/scripts/kb061_run_periodic_sync.sh
```

Secrets stay in gitignored `.secrets/` (`soc_sync_api_key`, optional `thehive_password`).
Wazuh-tagged TheHive alerts are mapped to **high** severity so control-plane **incidents** are created.

## Validation

```bash
cd /opt/mssp-control
./scripts/kb061_validate_thehive_control_plane_sync.sh
```

Expected:

```text
KB-061 THEHIVE CONTROL PLANE SYNC VALIDATION PASSED
```

## Must not change

- Customer forbidden fields / customer UI calling `/admin`
- Committing `.env` or `.secrets/`
