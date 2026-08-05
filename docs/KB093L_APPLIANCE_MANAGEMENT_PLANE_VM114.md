# Appliance Management plane (VM 114) — channel gateway off VM 100

Status: Live (2026-08-05)  
Related: KB-093 §12, Track-4 channel/OTA

## What changed

| Item | Before | After |
|------|--------|--------|
| Channel / register / heartbeat edge | Co-located on **VM 100** `mssp-control` | Dedicated **VM 114** `junexis-appliance-mgmt` (`192.168.0.224`) |
| Admin / Customer portals + Postgres SoR | VM 100 | **Still VM 100** (unchanged) |
| Disposable ISO factory **VM 113** | Idle stopped VM | **Destroyed** (recreate with `junexis-appliance/scripts/b2_proxmox_create_build_vm.sh` when next ISO build is needed) |

## VM 114 facts

| Item | Value |
|------|--------|
| Proxmox VMID | **114** |
| Name | `junexis-appliance-mgmt` |
| IP | **192.168.0.224/24** |
| Specs | 2 vCPU, 4 GiB RAM, 40 GiB disk, `onboot=1` |
| API | `http://192.168.0.224:8000` |
| Entrypoint | `app.main_appliance_mgmt:app` (appliance routes only) |
| DB/Redis | SSH tunnel from 114 → VM100 **loopback** (`junexis-db-tunnel.service`) — Postgres/Redis are **not** LAN-published |

## Dual-run (safe cutover)

Until every appliance/`junexis-channeld` is pointed at `.224`, both planes answer the same appliance routes:

- Control plane (legacy): `http://192.168.0.201:8000`
- Appliance Management (target): `http://192.168.0.224:8000`

Admin enqueue UI can stay on VM 100 (same PostgreSQL). Appliances should **poll/connect channel on VM 114**.

### You do **not** need to memorize a gateway URL

Lab images and CLI already default to VM 114:

| Mechanism | What happens |
|-----------|----------------|
| `junexis-cli setup` / `register` | Default `--control-plane` = `http://192.168.0.224:8000` |
| ISO Ansible `group_vars` | Bakes the same URL into `/etc/junexis/channel.yaml` |
| Admin → Create activation token | Shows a **Copy register command** button with gateway + token filled in |

**New appliance workflow (remember this, not the IP):**

1. Admin → Appliances → create activation token for the tenant  
2. Click **Copy register command**  
3. On the appliance: paste and run that one command  
4. Done — channel/heartbeat use Appliance Management automatically  

Production public edge later: set `JUNEXIS_DEFAULT_CONTROL_PLANE=https://soc.junexis.com` when building the customer ISO (and matching Admin `VITE_APPLIANCE_GATEWAY_URL`).

### Manual override (rare)

```bash
export JUNEXIS_CONTROL_PLANE=http://192.168.0.224:8000
sudo systemctl restart junexis-channeld
```

## Operator scripts (from VM 100)

```bash
# Create VM (idempotent if 114 exists)
./scripts/appliance_mgmt/create_proxmox_vm.sh

# Deploy / refresh API + tunnel
./scripts/appliance_mgmt/deploy_appliance_mgmt.sh
```

Compose overlay on VM 100 (loopback DB publish only):

`docker-compose.appliance-mgmt-db-expose.yml`

## Smoke checks

```bash
curl -fsS http://192.168.0.224:8000/health
# expect: "service":"junexis-appliance-mgmt","api":"ok","database":"ok","redis":"ok"

curl -sS -o /dev/null -w '%{http_code}\n' http://192.168.0.224:8000/appliance/channel/poll
# expect: 401

curl -fsS http://127.0.0.1:8000/health   # control plane still ok
```

## Rebuild the install ISO later (what “recreate the build factory” means)

Think of **VM 113** as a temporary workshop, not a permanent server:

1. When you need a **new** Junexis install ISO/qcow2, we create VM 113 again (script does this).  
2. The workshop builds the image and copies artifacts to VM 100 (`.cache/dist*`).  
3. Then we can **delete VM 113 again** so Proxmox RAM/disk stay free.

You only recreate it when you intentionally rebuild the customer install media — not for day-to-day appliance operation. Day-to-day appliances talk to **VM 114**, which stays on.

- TLS / `soc.junexis.com` front door for appliances
- Remove appliance channel routes from VM 100 `app.main` after all appliances cut over
- Rotate bootstrap cloud-init password on VM 114; dedicated SSH keys (not packer build key)
- Appliance CA + OTA blob repo hosts on this plane
