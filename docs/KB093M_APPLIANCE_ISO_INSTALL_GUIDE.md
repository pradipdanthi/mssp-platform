# Junexis Appliance — how to install (Track 5)

## Download (re-download after every “go” rebuild)

WinSCP: enable **Show hidden files**, then get:

`/opt/mssp-control/junexis-appliance/.cache/dist-install/Junexis-Appliance-Install-v0.1.0-dev.iso`

Current build (harden + splash + idle engines):

- **SHA256:** `8722dc083f1cb7b6e99784e5af2d71c4320d5a1b43390d7170435273b62e62be`
- Built: 2026-08-05 ~23:56

## What you should see

| Screen | What to do |
|--------|------------|
| GRUB | **Install Junexis Appliance (automatic…)** — Enter or wait 5 seconds |
| Ubuntu Server vs Minimized | **Must not appear** |
| After install / later boots | Black splash: **JUNEXIS APPLIANCE** (yellow→red) + **Your Dedicated SOC Sentinel** (white) ~3 seconds |

## What the ISO does automatically

1. Installs **ubuntu-server-minimal** (unattended)
2. Firstboot: **minimize** (strip fluff) + **harden** (CIS-style) + firewall/audit/AppArmor
3. Installs **all catalogue engines svc-01…10 idle** until license
4. Installs Junexis Plymouth splash
5. **Never** installs TheHive/Shuffle

## Login after install

- User: `junexis`
- Password: `ChangeMeNow!` (change after register)
- Firstboot log: `/var/log/junexis/firstboot.log` (give it several minutes)

## Track 5 next

Admin → Appliances → create token → **Copy register command** → paste on appliance.
