# Kevantic CLI Specification — `kevantic-cli`

Status: Specification (KB-093). Implementation lives under `cli/kevantic-cli/`.  
Audience: field engineers and SOC operators on a stripped Ubuntu Server appliance.

---

## 1. Purpose

`kevantic-cli` is the **only supported local management surface** on the Kevantic Hardened On-Prem Appliance. It configures identity, licensing/entitlements, channel health, modular services, OTA/WPK staging, and cryptographic offboarding — without requiring inbound remote access.

It is **not** a customer portal, not a Wazuh Dashboard wrapper, and not a second endpoint agent.

Binary install path (target image): `/usr/bin/kevantic-cli`  
Config: `/etc/kevantic/cli.yaml` + drop-ins in `/etc/kevantic/cli.d/`  
State: `/var/lib/kevantic/`  
Logs: `journalctl -u kevantic-channeld` / `journalctl -t kevantic-cli`

---

## 2. Design principles

1. **Works offline** for activation, status, and service enable when a signed license blob is provided.
2. **Never prints secrets** (activation tokens, API keys, private keys, cert PEMs) unless `--reveal-once` is used on an interactive TTY and the value is newly generated.
3. **Root or `kevantic` group** for mutating commands; read-only status may run as `kevantic`.
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

### 4.1 `kevantic-cli version`

Print CLI, appliance software train (`VERSION`), OS kernel, channel protocol version.

### 4.2 `kevantic-cli status`

Summarize:

- Appliance ID / registration state (`unregistered` \| `registered` \| `decommissioned`)
- **Network mode** (`bootstrap` \| `locked`) and last bootstrap result
- Channel state (`disconnected` \| `connecting` \| `ready` \| `degraded`)
- Last successful heartbeat / control receive
- Entitlements (service id → enabled/disabled, expiry)
- Disk / LUKS unlock health (no passphrase)
- Core units: `kevantic-channeld`, container runtime, local Wazuh manager (if core)

### 4.3 `kevantic-cli setup`

Interactive (or flagged) first-boot wizard:

```text
kevantic-cli setup \
  --token <ACTIVATION_TOKEN> \
  --control-plane https://soc.kevantic.com \
  --appliance-name <NAME> \
  [--site-name <SITE>] \
  [--proxy URL] \
  [--deploy-method factory|customer-vm]
```

**Flow:**

1. Collect/confirm network (DHCP or static via netplan helpers). Leave mode **bootstrap** until updates finish.
2. Hardware fingerprint (TPM EK pub hash if present, else product UUID + disk serial + MAC set — hashed).
3. Redeem token against control plane (Phase A: KB-016 `POST /appliance/register`; Phase B: mTLS CSR exchange — see KB-093).
4. Store durable credential/cert under `/var/lib/kevantic/secrets/` (0600).
5. Enable and start `kevantic-channeld` (may be deferred until after bootstrap if policy requires).
6. Write local config; show **once** any one-time secrets.
7. Remind engineer to run `bootstrap update` then `network lock` before handoff.

Compatible with Admin-generated activation tokens (KB-015/016). Same commands for **factory physical** and **customer VM** installs (single ISO).

### 4.3a `kevantic-cli bootstrap` / `kevantic-cli network`

First-time critical patching and network posture (KB-093 §3.1):

```text
kevantic-cli bootstrap status
kevantic-cli bootstrap update [--os-only] [--engines-only] [--proxy URL]
kevantic-cli network status
kevantic-cli network lock --yes
kevantic-cli network unlock --yes --confirm BREAK_GLASS   # audited; temporary Internet again
```

| Command | Behavior |
|---------|----------|
| `bootstrap update` | While in **bootstrap** mode, allow outbound Internet to Ubuntu security + Kevantic-approved engine endpoints; apply **critical** OS and backend engine patches; record success/fail |
| `network lock` | Switch nftables/policy to **LOCKED**: LAN/VPC agent ingest in; **only** SOC secure channel out; clear general Internet egress |
| `network unlock` | Break-glass return to bootstrap egress (dual confirmation + audit); must `lock` again before production |

Handoff checklist: `bootstrap status` = success **and** `network status` = `locked`.

### 4.4 `kevantic-cli register` / `kevantic-cli heartbeat`

Non-interactive equivalents for automation/tests. Prefer `setup` in the field.

- `register` — token redemption only  
- `heartbeat` — force one health push (also used by systemd timer as fallback to channel)

### 4.5 `kevantic-cli channel`

| Subcommand | Action |
|------------|--------|
| `channel status` | Connection, cert notAfter, last RTT |
| `channel reconnect` | Bounce WebSocket/NATS client |
| `channel doctor` | DNS, TCP/443, TLS handshake, clock skew, proxy |

### 4.6 Licensing & entitlements

#### Online (preferred)

Entitlements arrive as **signed activation payloads** on the outbound channel. The license enforcer verifies signature, writes `/var/lib/kevantic/entitlements.json`, and asks `service_manager` to reconcile units.

#### Offline / air-gapped

```text
kevantic-cli license show
kevantic-cli license apply --file /path/to/entitlement.jws
kevantic-cli enable-service --key <SIGNED_TOTP_OR_LICENSE_BLOB>
kevantic-cli disable-service --id svc-04
```

`enable-service --key`:

1. Parse JWS / signed license string (Ed25519 or ECDSA P-256).
2. Verify against embedded Kevantic public verify key(s) in `/etc/kevantic/trust/`.
3. Check `appliance_id` binding (or fingerprint claim), `not_before` / `not_after`, nonce replay cache.
4. Enable listed `service_ids`; optionally trigger OTA image pull when online.

`disable-service` may require SOC signature or local break-glass with dual confirmation.

### 4.7 Services

```text
kevantic-cli services list
kevantic-cli services status [--id svc-06]
kevantic-cli services logs --id svc-06 [--since 1h]
```

Mutating start/stop **without** a valid entitlement is rejected (except `svc-01` / `svc-02` core when product policy marks them always-on for appliance SKUs).

### 4.8 OTA / agent staging

```text
kevantic-cli ota status
kevantic-cli ota check
kevantic-cli ota apply --manifest /var/lib/kevantic/ota/pending/*.json   # after verify
kevantic-cli wpk list
kevantic-cli wpk stage --file <agent.wpk>
kevantic-cli wpk promote --version X.Y.Z    # expose to local Wazuh agent_upgrade
```

OTA never auto-reboots collector-critical services without `--allow-disruptive` and maintenance window flag from channel or CLI.

### 4.9 Network helpers

```text
kevantic-cli net show
kevantic-cli net set-static --iface eth0 --address CIDR --gateway IP --dns IP[,IP]
kevantic-cli net set-dhcp --iface eth0
```

Uses netplan under the hood; validates before apply.

### 4.10 Offboarding / wipe

```text
kevantic-cli offboard --yes --confirm DECOMMISSION
kevantic-cli wipe --yes --confirm CRYPTOGRAPHIC_WIPE
```

**`offboard`:**

1. Send decommission intent on channel (if up).
2. Stop all kevantic services; revoke local client cert (delete key material).
3. Purge configs under `/etc/kevantic` (keep a tombstone `decommissioned` flag).
4. Lock console to break-glass only if policy requires.

**`wipe`:**

1. Assumes offboard completed or forced.
2. `shred` / `wipefs` of secret volumes and keyslots where safe; clear LUKS key material from memory/disk per runbook.
3. Secure-erase OTA/WPK/log pools under `/var/lib/kevantic`.
4. Irreversible — requires exact confirmation string.

Cloud CA revocation is performed by the control plane when it receives the decommission signal or Admin triggers offboard.

### 4.11 Diagnostics (safe)

```text
kevantic-cli doctor
kevantic-cli support-bundle --out /tmp/kevantic-bundle.tgz
```

Support bundle **redacts** secrets, raw payloads, and customer log bodies by default. Include raw only with `--include-local-logs` (stays on-prem; never auto-uploaded).

---

## 5. Config schema (sketch)

`/etc/kevantic/cli.yaml`:

```yaml
appliance:
  name: ""
  site_name: ""
control_plane:
  base_url: "https://soc.kevantic.com"
  channel_url: "wss://soc.kevantic.com/appliance/v1/channel"
channel:
  protocol: "mtls-websocket"   # future: nats-leaf
  heartbeat_seconds: 30
trust:
  verify_keys_dir: /etc/kevantic/trust
paths:
  secrets: /var/lib/kevantic/secrets
  entitlements: /var/lib/kevantic/entitlements.json
  ota: /var/lib/kevantic/ota
  wpk: /var/lib/kevantic/wpk
```

---

## 6. Entitlement payload (offline key)

JWS compact serialization. Claims (JWT-like):

| Claim | Meaning |
|-------|---------|
| `iss` | `kevantic-licensing` |
| `sub` | appliance UUID |
| `aud` | `kevantic-appliance` |
| `iat` / `exp` | validity |
| `jti` | replay id |
| `svc` | array of `svc-NN` to enable |
| `fp` | optional hardware fingerprint hash |
| `features` | optional feature flags (agent modules, etc.) |

Public verify keys ship in the ISO; private signing keys never leave Kevantic CA/HSM.

---

## 7. Implementation notes

| Topic | Decision |
|-------|----------|
| Language | Go 1.22+ preferred (static binary on minimal OS); Python 3 acceptable if already required by runtime |
| Privileges | setuid **not** used; polkit or root/`kevantic` group |
| Tests | unit tests for license verify + golden CLI `--help`; integration against mock channel |
| Packaging | `.deb` `kevantic-cli` built in CI and installed by Ansible `kevantic_runtime` |

---

## 8. Non-goals (this version)

- Full interactive TUI dashboard
- Direct editing of Wazuh `ossec.conf` without validation
- Customer-facing multi-tenant admin (that stays in Kevantic Admin portal)
- Opening inbound SSH from Kevantic cloud (outbound channel only)
- Installing **TheHive** or any local ticketing/case UI on the appliance
- Leaving general Internet egress enabled after bootstrap (must `network lock`)

---

## 9. Example field session

```bash
# Same ISO on physical (factory) or customer VM
sudo kevantic-cli setup --token "$TOKEN" --appliance-name "ACME-EDGE-01" --deploy-method customer-vm
sudo kevantic-cli bootstrap update
sudo kevantic-cli network lock --yes
sudo kevantic-cli status --json
sudo kevantic-cli enable-service --key "$OFFLINE_LICENSE"
sudo kevantic-cli services list
sudo kevantic-cli doctor
```
