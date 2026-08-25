# Bare-metal recovery (Proxmox wiped)

## Do you need a Proxmox backup?

**Nice to have, not required.**

- **Required:** ability to install Proxmox again on the hardware (ISO/USB installer).
- **Optional Proxmox backup:** saved network bridges (`vmbr0`, capture bridge), ISO library, VM templates — saves time.
- **Guest data / MSSP:** comes from `MSSP_Full_Backup` (Path A), not from Proxmox host backup.

If Proxmox is formatted: reinstall Proxmox → recreate bridges → Path A.

## Does Ansible VM (112) have to exist?

**Yes — required for a complete restore.** VM 112 (`automation` / `192.168.0.222`) is the dedicated Ansible controller. Path A backups include it (`remote/vm112_*` in the encrypted archive: `mssp-automation` tree + controller SSH keys).

Recreate VM 112 with the other core guests, then restore those captured paths before running playbooks from 112.

Emergency fallback only: playbooks also exist under restored `/opt/mssp-control/ansible` on VM 100 if 112 is temporarily down — but the supported DR end-state is **112 online and working**.

## Clean-system sequence

1. Install Proxmox on bare metal.
2. Configure LAN bridge (same subnet `192.168.0.0/24` recommended).
3. Add Ubuntu Server LTS ISO to Proxmox storage.
4. Prompt Cursor: Path A from the complete backup folder (or Drive tar).
5. Cursor creates VMs **100 / 101 / 102 / 106 / 109 / 112**, restores control plane + DB, restores VM 112 Ansible tree/keys, redeploys engines.
