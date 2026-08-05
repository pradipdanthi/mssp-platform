# Junexis Appliance — how to install (Track 5)

## What you should see

| Screen | What to do |
|--------|------------|
| GRUB menu | Leave default / press Enter on **Install Junexis Appliance (automatic…)** — wait 5 seconds and it starts alone |
| Ubuntu language / Server vs Minimized / user setup | **You should NOT see these.** If you do, you are on an old ISO — re-download from VM 100 |

There is **no** choice of “Ubuntu Server” vs “Minimized” on the fixed ISO. It forces **ubuntu-server-minimal**, then firstboot **chops + hardens** (Ansible minimize + CIS).

## Login after install

- User: `junexis`
- Password: `ChangeMeNow!` (change after register)
- Hostname: `junexis-appliance`

First reboot runs `junexis-firstboot` (minimize/harden/engines). Give it several minutes; check `/var/log/junexis/firstboot.log` if unsure.

## Then Track 5

Admin → Appliances → create token → **Copy register command** → paste on the appliance.

## Download path (WinSCP: show hidden files)

`/opt/mssp-control/junexis-appliance/.cache/dist-install/Junexis-Appliance-Install-v0.1.0-dev.iso`
