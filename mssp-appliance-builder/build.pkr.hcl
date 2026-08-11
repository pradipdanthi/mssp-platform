# Packer HCL2 — MSSP tamper-proof Ubuntu 24.04 appliance (Proxmox-native)
#
# Architecture (no nested KVM):
#   Proxmox host  — boots the install guest from Ubuntu ISO (proxmox-iso builder)
#   VM 112        — Ansible controller runs hardening playbook over SSH
#   post-process  — export raw disk → scripts/convert_verity.sh (UKI + dm-verity)
#
# Usage (from VM 100 / operator workstation with Proxmox API access):
#   cd mssp-appliance-builder
#   packer init .
#   packer build -var-file=vars/lab.pkrvars.hcl .
#
# Temporary build password must match http/user-data identity.

packer {
  required_version = ">= 1.9.0"
  required_plugins {
    proxmox = {
      source  = "github.com/hashicorp/proxmox"
      version = ">= 1.1.0"
    }
  }
}

variable "proxmox_url" {
  type        = string
  description = "Proxmox API URL, e.g. https://192.168.0.191:8006/api2/json"
}

variable "proxmox_username" {
  type        = string
  description = "API user or token id (e.g. packer@pve!golden)"
  default     = "root@pam"
}

variable "proxmox_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "proxmox_token" {
  type        = string
  description = "API token UUID secret when username is user@realm!tokenid"
  sensitive   = true
  default     = ""
}

variable "proxmox_node" {
  type    = string
  default = "Labhyp"
}

variable "proxmox_storage" {
  type    = string
  default = "local-zfs"
}

variable "proxmox_iso_storage" {
  type    = string
  default = "local"
}

variable "ubuntu_iso_file" {
  type        = string
  description = "Ubuntu install ISO on Proxmox, e.g. local:iso/ubuntu-24.04.4-live-server-amd64.iso"
}

variable "cidata_iso_file" {
  type        = string
  description = "Prebuilt cidata ISO on Proxmox (meta-data + user-data). Built by scripts/build_cidata_iso.sh"
  default     = "local:iso/mssp-appliance-cidata.iso"
}

variable "bridge" {
  type    = string
  default = "vmbr0"
}

variable "vm_id" {
  type        = number
  description = "Ephemeral install VMID (destroyed after export). Avoid 100–114."
  default     = 199
}

variable "vm_cpus" {
  type    = number
  default = 4
}

variable "vm_memory_mb" {
  type    = number
  default = 8192
}

variable "disk_size" {
  type    = string
  default = "40G"
}

variable "ssh_username" {
  type    = string
  default = "packer"
}

variable "ssh_password" {
  type      = string
  default   = "PackerBuildOnlyChangeMe!"
  sensitive = true
}

variable "ansible_controller_host" {
  type        = string
  description = "VM 112 automation controller"
  default     = "192.168.0.222"
}

variable "ansible_controller_user" {
  type    = string
  default = "secadmin"
}

variable "ansible_controller_ssh_key" {
  type    = string
  default = "~/.ssh/id_ed25519_automation"
}

variable "output_directory" {
  type    = string
  default = "output-mssp-appliance"
}

variable "insecure_skip_tls_verify" {
  type    = bool
  default = true
}

locals {
  timestamp = formatdate("YYYYMMDD-hhmmss", timestamp())
  vm_name   = "mssp-appliance-build-${local.timestamp}"
}

source "proxmox-iso" "ubuntu2404" {
  proxmox_url              = var.proxmox_url
  username                 = var.proxmox_username
  password                 = var.proxmox_password != "" ? var.proxmox_password : null
  token                    = var.proxmox_token != "" ? var.proxmox_token : null
  insecure_skip_tls_verify = var.insecure_skip_tls_verify
  node                     = var.proxmox_node

  vm_id                = var.vm_id
  vm_name              = local.vm_name
  template_name        = "mssp-appliance-${local.timestamp}"
  template_description = "MSSP immutable appliance (pre-verity) — Packer proxmox-iso"

  iso_file         = var.ubuntu_iso_file
  iso_storage_pool = var.proxmox_iso_storage
  unmount_iso      = true

  # cidata ISO (reliable autoinstall — same pattern as kevantic-appliance/packer)
  additional_iso_files {
    type             = "ide"
    index            = "0"
    iso_file         = var.cidata_iso_file
    iso_storage_pool = var.proxmox_iso_storage
    unmount          = true
  }

  boot      = "order=ide2;ide0;scsi0;net0"
  boot_wait = "12s"
  boot_command = [
    "<esc><esc><esc><wait>",
    "e<wait>",
    "<down><down><down><end>",
    " autoinstall ds=nocloud ---",
    "<f10>"
  ]

  ssh_private_key_file      = "${path.root}/../kevantic-appliance/.tools/build-ssh/kevantic_packer"
  ssh_clear_authorized_keys = false
  ssh_handshake_attempts    = 600
  ssh_timeout               = "25m"

  qemu_agent = true
  os         = "l26"
  cores      = var.vm_cpus
  memory     = var.vm_memory_mb
  sockets    = 1
  cpu_type   = "host"
  scsi_controller = "virtio-scsi-single"

  disks {
    type         = "scsi"
    disk_size    = var.disk_size
    storage_pool = var.proxmox_storage
    format       = "raw"
    io_thread    = true
  }

  network_adapters {
    model  = "virtio"
    bridge = var.bridge
    firewall = false
  }

  ssh_username = var.ssh_username
  ssh_password = var.ssh_password

  cloud_init = false
}

build {
  name    = "mssp-appliance-proxmox"
  sources = ["source.proxmox-iso.ubuntu2404"]

  # Ensure build SSH key is present (also seeded via autoinstall) and capture guest IP.
  provisioner "shell" {
    inline = [
      "set -euo pipefail",
      "install -d -m 700 /home/packer/.ssh",
      "grep -q 'kevantic-packer-build-only' /home/packer/.ssh/authorized_keys 2>/dev/null || echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEZ0FCM2Njl7mYWRkJBCWf4G8SDSMT1OhZ5G/tWJTBEJ kevantic-packer-build-only' >> /home/packer/.ssh/authorized_keys",
      "chown -R packer:packer /home/packer/.ssh",
      "chmod 600 /home/packer/.ssh/authorized_keys",
      "ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | head -1 > /tmp/mssp_guest_ip",
      "cat /tmp/mssp_guest_ip",
    ]
  }

  provisioner "file" {
    source      = "/tmp/mssp_guest_ip"
    destination = "${path.root}/.cache/mssp_guest_ip"
    direction   = "download"
  }

  # Ansible runs ON VM 112, targeting this ephemeral Proxmox guest (no nested KVM).
  provisioner "shell-local" {
    inline = [
      "set -euo pipefail",
      "mkdir -p '${path.root}/.cache'",
      "HOST=$(tr -d '[:space:]' < '${path.root}/.cache/mssp_guest_ip')",
      "test -n \"$HOST\"",
      "export MSSP_TARGET_HOST=\"$HOST\"",
      "export MSSP_TARGET_USER='${var.ssh_username}'",
      "export MSSP_TARGET_PASSWORD='${var.ssh_password}'",
      "export MSSP_ANSIBLE_CONTROLLER='${var.ansible_controller_host}'",
      "export MSSP_ANSIBLE_CONTROLLER_USER='${var.ansible_controller_user}'",
      "export MSSP_ANSIBLE_CONTROLLER_KEY='${var.ansible_controller_ssh_key}'",
      "export MSSP_BUILDER_ROOT='${path.root}'",
      "chmod +x '${path.root}/scripts/provision_via_vm112.sh'",
      "'${path.root}/scripts/provision_via_vm112.sh'",
    ]
  }

  # After Packer converts the guest to a template, export + verity are operator/CI steps:
  #   scripts/export_and_convert_verity.sh <vmid-or-template>
  post-processor "shell-local" {
    inline = [
      "set -euo pipefail",
      "mkdir -p '${var.output_directory}'",
      "echo \"Template ready on Proxmox node ${var.proxmox_node}. Next:\"",
      "echo \"  sudo ${path.root}/scripts/export_and_convert_verity.sh --vmid ${var.vm_id} --out '${var.output_directory}'\"",
      "echo PROXMOX_PACKER_BUILD_OK | tee '${var.output_directory}/BUILD_OK'",
    ]
  }
}
