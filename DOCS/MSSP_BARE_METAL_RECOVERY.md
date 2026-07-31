# Bare-metal recovery (Proxmox wiped)

## Do you need a Proxmox backup?

**Nice to have, not required.**

- **Required:** ability to install Proxmox again on the hardware (ISO/USB installer).
- **Optional Proxmox backup:** saved network bridges (`vmbr0`, capture bridge), ISO library, VM templates — saves time.
- **Guest data / MSSP:** comes from `MSSP_Full_Backup` (Path A), not from Proxmox host backup.

If Proxmox is formatted: reinstall Proxmox → recreate bridges → Path A.

## Does Ansible VM (112) have to exist?

**No.** Inventory lists VM 112 as automation controller, but recovery can run Ansible **from restored VM 100** (or from Cursor’s SSH session on VM 100) using:

- playbooks/roles in `mssp-control/ansible/`
- inventory `ansible/inventory/hosts.yml`
- SSH keys (must be available — preferably stored encrypted next to the DR package)

Rebuild VM 112 later if you want a dedicated controller again.

## Clean-system sequence

1. Install Proxmox on bare metal.
2. Configure LAN bridge (same subnet `192.168.0.0/24` recommended).
3. Add Ubuntu Server LTS ISO to Proxmox storage.
4. Prompt Cursor: Path A from `MSSP_Full_Backup`.
5. Cursor creates VMs 100/101/102/106/109/(112), restores control plane + DB, runs ansible for engines.
