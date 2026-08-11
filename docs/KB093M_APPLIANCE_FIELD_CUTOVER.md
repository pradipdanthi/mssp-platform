# KB-093M — Track 5: First appliance field cutover (E2E)

Status: **Paused** — waiting on **KB-093N Phase N1** (immutable mkosi image).  
Date: 2026-08-05 (strategy reset 2026-08-06)  
Depends on: Tracks 1–4 + KB-093L (VM 114) + KB-093N N1 lab image  

> Do **not** ship or continue Track 5 on the retired Subiquity remaster ISO.  
> See `docs/KB093N_IMMUTABLE_APPLIANCE_IMAGE_STRATEGY.md`.

## Goal (plain English)

Prove you can stand up a **real** Junexis appliance that:

1. Registers through **VM 114** (not by memorizing IPs)
2. Heartbeats and shows up in Admin
3. Channel/poll works against the Appliance Management plane
4. Uses the Admin **Copy register command** flow

Track 5 from the older “wider platform” list (Zeek/MISP/Velociraptor/AI workers) stays **paused** unless you say otherwise. This Track 5 is **appliance field cutover**.

## Checklist

| # | Task | Done when |
|---|------|-----------|
| **5.1** | Register path smoke against VM 114 | Script creates activation token → `POST /appliance/register` on `.224` succeeds (or clean 4xx with clear reason) — **partial**: route smoke PASS; full live register when `PLATFORM_ADMIN_PASSWORD` is set |
| **5.2** | Operator one-pager in Admin | Appliances page shows the 4-step “new appliance” workflow — **done** |
| **5.3** | First appliance boots to register | Use the **existing ready ISO** (or any lab VM from it); run the copied register command; appliance appears Online — **no rebuild required** |
| **5.4** | Heartbeat + channel after register | Heartbeat timer + channeld status OK; Admin shows enabled_services |
| **5.5** | Dual-run decision | Either keep VM100 appliance routes as fallback **or** document “VM114 only” after all lab appliances cut over |

## What you remember (only this)

1. Admin → Appliances → create token  
2. **Copy register command**  
3. Paste on the appliance  
4. Confirm Online in Admin  

Gateway URL is already baked into lab defaults (KB-093L).

## Validation

```bash
cd /opt/mssp-control
./scripts/kb093m_validate_appliance_field_cutover.sh
```

Expected final line: `KB093M_VALIDATE_PASS`
