# Lab defaults for Proxmox-native Packer build (no nested KVM).
# Copy secrets via env — do NOT commit real passwords/tokens:
#   export PKR_VAR_proxmox_password='...'
#   # or: export PKR_VAR_proxmox_token='root@pam!packer=...'

proxmox_url  = "https://192.168.0.191:8006/api2/json"
proxmox_node = "Labhyp"
proxmox_storage = "local-zfs"
ubuntu_iso_file = "local:iso/ubuntu-24.04.4-live-server-amd64.iso"

vm_id         = 199
vm_cpus       = 4
vm_memory_mb  = 8192
disk_size     = "64G"

ansible_controller_host    = "192.168.0.222"
ansible_controller_user    = "secadmin"
ansible_controller_ssh_key = "~/.ssh/id_ed25519_automation"

output_directory = "output-mssp-appliance"
insecure_skip_tls_verify = true
