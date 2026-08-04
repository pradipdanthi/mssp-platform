# Junexis CLI Specification — `junexis-cli`

Status: Specification (KB-093). Implementation lives under `cli/junexis-cli/`.  
Audience: field engineers and SOC operators on a stripped Ubuntu Server appliance.

---

## 1. Purpose

`junexis-cli` is the **only supported local management surface** on the Junexis Hardened On-Prem Appliance. It configures identity, licensing/entitlements, channel health, modular services, OTA/WPK staging, and cryptographic offboarding — without requiring inbound remote access.

It is **not** a customer portal, not a Wazuh Dashboard wrapper, and not a second endpoint agent.

Binary install path (target image): `/usr/bin/junexis-cli`  
Config: `/etc/junexis/cli.yaml` + drop-ins in `/etc/junexis/cli.d/`  
State: `/var/lib/junexis/`  
Logs: `journalctl -u junexis-channeld` / `journalctl -t junexis-cli`

---

## 2. Design principles

1. **Works offline** for activation, status, and service enable when a signed license blob is provided.
2. **Never prints secrets** (activation tokens, API keys, private keys, cert PEMs) unless `--reveal-once` is used on an interactive TTY and the value is newly generated.
3. **Root or `junexis` group** for mutating commands; read-only status may run as `junexis`.
4. **Idempotent** where practical (`setup`, `enable-service`, `channel reconnect`).
5. **Machine-readable** output via `--json` for automation.
6. **Fail closed** — unknown service IDs, bad signatures, clock skew beyond policy → non-zero exit.

---

## 3. Global flags

| Flag | Meaning |
|------|---------|
| `--json` | Structured JSON on stdout; human text on stderr for progress |
| `--config PATH` | Override config file |
| `--quiet` / `-q` | Errors only |
| `--yes` / `-y` | Skip confirmation prompts (required for wipe/offboard) |
| `--timeout SEC` | Network/channel operation timeout (default 60) |

Exit codes: `0` ok · `1` usage/validation · `2` auth/license · `3` channel/network · `4` service failure · `10` destructive op aborted · `20` internal

---

## 4. Command reference

### 4.1 `junexis-cli version`

Print CLI, appliance software train (`VERSION`), OS kernel, channel protocol version.

### 4.2 `junexis-cli status`

Summarize:

- Appliance ID / registration state (`unregistered` \| `registered` \| `decommissioned`)
- **Network mode** (`bootstrap` \| `locked`) and last bootstrap result
- Channel state (`disconnected` \| `connecting` \| `ready` \| `degraded`)
- Last successful heartbeat / control receive
- Entitlements (service id → enabled/disabled, expiry)
- Disk / LUKS unlock health (no passphrase)
- Core units: `junexis-channeld`, container runtime, local Wazuh manager (if core)

### 4.3 `junexis-cli setup`

Interactive (or flagged) first-boot wizard:

```text
junexis-cli setup \
  --token <ACTIVATION_TOKEN> \
  --control-plane https://soc.junexis.com \
  --appliance-name <NAME> \
  [--site-name <SITE>] \
  [--proxy URL] \
  [--deploy-method factory|customer-vm]
```

**Flow:**

1. Collect/confirm network (DHCP or static via netplan helpers). Leave mode **bootstrap** until updates finish.
2. Hardware fingerprint (TPM EK pub hash if present, else product UUID + disk serial + MAC set — hashed).
3. Redeem token against control plane (Phase A: KB-016 `POST /appliance/register`; Phase B: mTLS CSR exchange — see KB-093).
4. Store durable credential/cert under `/var/lib/junexis/secrets/` (0600).
5. Enable and start `junexis-channeld` (may be deferred until after bootstrap if policy requires).
6. Write local config; show **once** any one-time secrets.
7. Remind engineer to run `bootstrap update` then `network lock` before handoff.

Compatible with Admin-generated activation tokens (KB-015/016). Same commands for **factory physical** and **customer VM** installs (single ISO).

### 4.3a `junexis-cli bootstrap` / `junexis-cli network`

First-time critical patching and network posture (KB-093 §3.1):

```text
junexis-cli bootstrap status
junexis-cli bootstrap update [--os-only] [--engines-only] [--proxy URL]
junexis-cli network status
junexis-cli network lock --yes
junexis-cli network unlock --yes --confirm BREAK_GLASS   # audited; temporary Internet again
```

| Command | Behavior |
|---------|----------|
| `bootstrap update` | While in **bootstrap** mode, allow outbound Internet to Ubuntu security + Junexis-approved engine endpoints; apply **critical** OS and backend engine patches; record success/fail |
| `network lock` | Switch nftables/policy to **LOCKED**: LAN/VPC agent ingest in; **only** SOC secure channel out; clear general Internet egress |
| `network unlock` | Break-glass return to bootstrap egress (dual confirmation + audit); must `lock` again before production |

Handoff checklist: `bootstrap status` = success **and** `network status` = `locked`.

### 4.4 `junexis-cli register` / `junexis-cli heartbeat`

Non-interactive equivalents for automation/tests. Prefer `setup` in the field.

- `register` — token redemption only  
- `heartbeat` — force one health push (also used by systemd timer as fallback to channel)

### 4.5 `junexis-cli channel`

| Subcommand | Action |
|------------|--------|
| `channel status` | Connection, cert notAfter, last RTT |
| `channel reconnect` | Bounce WebSocket/NATS client |
| `channel doctor` | DNS, TCP/443, TLS handshake, clock skew, proxy |

### 4.6 Licensing & entitlements

#### Online (preferred)

Entitlements arrive as **signed activation payloads** on the outbound channel. The license enforcer verifies signature, writes `/var/lib/junexis/entitlements.json`, and asks `service_manager` to reconcile units.

#### Offline / air-gapped

```text
junexis-cli license show
junexis-cli license apply --file /path/to/entitlement.jws
junexis-cli enable-service --key <SIGNED_TOTP_OR_LICENSE_BLOB>
junexis-cli disable-service --id svc-04
```

`enable-service --key`:

1. Parse JWS / signed license string (Ed25519 or ECDSA P-256).
2. Verify against embedded Junexis public verify key(s) in `/etc/junexis/trust/`.
3. Check `appliance_id` binding (or fingerprint claim), `not_before` / `not_after`, nonce replay cache.
4. Enable listed `service_ids`; optionally trigger OTA image pull when online.

`disable-service` may require SOC signature or local break-glass with dual confirmation.

### 4.7 Services

```text
junexis-cli services list
junexis-cli services status [--id svc-06]
junexis-cli services logs --id svc-06 [--since 1h]
```

Mutating start/stop **without** a valid entitlement is rejected (except `svc-01` / `svc-02` core when product policy marks them always-on for appliance SKUs).

### 4.8 OTA / agent staging

```text
junexis-cli ota status
junexis-cli ota check
junexis-cli ota apply --manifest /var/lib/junexis/ota/pending/*.json   # after verify
junexis-cli wpk list
junexis-cli wpk stage --file <agent.wpk>
junexis-cli wpk promote --version X.Y.Z    # expose to local Wazuh agent_upgrade
```

OTA never auto-reboots collector-critical services without `--allow-disruptive` and maintenance window flag from channel or CLI.

### 4.9 Network helpers

```text
junexis-cli net show
junexis-cli net set-static --iface eth0 --address CIDR --gateway IP --dns IP[,IP]
junexis-cli net set-dhcp --iface eth0
```

Uses netplan under the hood; validates before apply.

### 4.10 Offboarding / wipe

```text
junexis-cli offboard --yes --confirm DECOMMISSION
junexis-cli wipe --yes --confirm CRYPTOGRAPHIC_WIPE
```

**`offboard`:**

1. Send decommission intent on channel (if up).
2. Stop all junexis services; revoke local client cert (delete key material).
3. Purge configs under `/etc/junexis` (keep a tombstone `decommissioned` flag).
4. Lock console to break-glass only if policy requires.

**`wipe`:**

1. Assumes offboard completed or forced.
2. `shred` / `wipefs` of secret volumes and keyslots where safe; clear LUKS key material from memory/disk per runbook.
3. Secure-erase OTA/WPK/log pools under `/var/lib/junexis`.
4. Irreversible — requires exact confirmation string.

Cloud CA revocation is performed by the control plane when it receives the decommission signal or Admin triggers offboard.

### 4.11 Diagnostics (safe)

```text
junexis-cli doctor
junexis-cli support-bundle --out /tmp/junexis-bundle.tgz
```

Support bundle **redacts** secrets, raw payloads, and customer log bodies by default. Include raw only with `--include-local-logs` (stays on-prem; never auto-uploaded).

---

## 5. Config schema (sketch)

`/etc/junexis/cli.yaml`:

```yaml
appliance:
  name: ""
  site_name: ""
control_plane:
  base_url: "https://soc.junexis.com"
  channel_url: "wss://soc.junexis.com/appliance/v1/channel"
channel:
  protocol: "mtls-websocket"   # future: nats-leaf
  heartbeat_seconds: 30
trust:
  verify_keys_dir: /etc/junexis/trust
paths:
  secrets: /var/lib/junexis/secrets
  entitlements: /var/lib/junexis/entitlements.json
  ota: /var/lib/junexis/ota
  wpk: /var/lib/junexis/wpk
```

---

## 6. Entitlement payload (offline key)

JWS compact serialization. Claims (JWT-like):

| Claim | Meaning |
|-------|---------|
| `iss` | `junexis-licensing` |
| `sub` | appliance UUID |
| `aud` | `junexis-appliance` |
| `iat` / `exp` | validity |
| `jti` | replay id |
| `svc` | array of `svc-NN` to enable |
| `fp` | optional hardware fingerprint hash |
| `features` | optional feature flags (agent modules, etc.) |

Public verify keys ship in the ISO; private signing keys never leave Junexis CA/HSM.

---

## 7. Implementation notes

| Topic | Decision |
|-------|----------|
| Language | Go 1.22+ preferred (static binary on minimal OS); Python 3 acceptable if already required by runtime |
| Privileges | setuid **not** used; polkit or root/`junexis` group |
| Tests | unit tests for license verify + golden CLI `--help`; integration against mock channel |
| Packaging | `.deb` `junexis-cli` built in CI and installed by Ansible `junexis_runtime` |

---

## 8. Non-goals (this version)

- Full interactive TUI dashboard
- Direct editing of Wazuh `ossec.conf` without validation
- Customer-facing multi-tenant admin (that stays in Junexis Admin portal)
- Opening inbound SSH from Junexis cloud (outbound channel only)
- Installing **TheHive** or any local ticketing/case UI on the appliance
- Leaving general Internet egress enabled after bootstrap (must `network lock`)

---

## 9. Example field session

```bash
# Same ISO on physical (factory) or customer VM
sudo junexis-cli setup --token "$TOKEN" --appliance-name "ACME-EDGE-01" --deploy-method customer-vm
sudo junexis-cli bootstrap update
sudo junexis-cli network lock --yes
sudo junexis-cli status --json
sudo junexis-cli enable-service --key "$OFFLINE_LICENSE"
sudo junexis-cli services list
sudo junexis-cli doctor
```
