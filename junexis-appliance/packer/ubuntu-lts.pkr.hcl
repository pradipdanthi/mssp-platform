# Junexis Appliance — Ubuntu Server 24.04 LTS Packer (B2)
# Build inside ci/Dockerfile.b2-builder (qemu + packer) — do not run minimize on mssp-control.

packer {
  required_version = ">= 1.9.0"
  required_plugins {
    qemu = {
      version = ">= 1.1.0"
      source  = "github.com/hashicorp/qemu"
    }
    ansible = {
      version = ">= 1.1.0"
      source  = "github.com/hashicorp/ansible"
    }
  }
}

variable "ubuntu_iso_url" {
  type        = string
  description = "Ubuntu 24.04 live-server ISO URL"
}

variable "ubuntu_iso_checksum" {
  type        = string
  description = "Checksum as file:SHA256 or sha256:..."
}

variable "appliance_version" {
  type    = string
  default = "0.1.0-dev"
}

variable "ssh_username" {
  type    = string
  default = "junexis"
}

variable "ssh_password" {
  type      = string
  default   = "JunexisBuildOnlyChangeMe"
  sensitive = true
}

variable "disk_size" {
  type    = string
  default = "20480M"
}

variable "memory" {
  type    = string
  default = "2048"
}

variable "cpus" {
  type    = number
  default = 2
}

variable "headless" {
  type    = bool
  default = true
}

variable "output_directory" {
  type    = string
  default = "output-junexis-appliance"
}

source "qemu" "ubuntu_lts" {
  iso_url      = var.ubuntu_iso_url
  iso_checksum = var.ubuntu_iso_checksum

  output_directory = var.output_directory
  shutdown_command = "echo '${var.ssh_password}' | sudo -S shutdown -P now"
  disk_size        = var.disk_size
  format           = "qcow2"
  accelerator      = "kvm"
  net_device       = "virtio-net"
  disk_interface   = "virtio"
  memory           = var.memory
  cpus             = var.cpus
  headless         = var.headless
  qemu_binary      = "qemu-system-x86_64"

  http_directory = "http"
  http_port_min  = 8200
  http_port_max  = 8299

  ssh_username     = var.ssh_username
  ssh_password     = var.ssh_password
  ssh_timeout      = "45m"
  ssh_handshake_attempts = 100

  boot_wait = "8s"
  boot_command = [
    "e<wait>",
    "<down><down><down><end>",
    " autoinstall ds=nocloud-net\\;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/ ---",
    "<f10>"
  ]

  vm_name = "junexis-appliance-${var.appliance_version}"
}

build {
  name    = "junexis-appliance"
  sources = ["source.qemu.ubuntu_lts"]

  provisioner "shell" {
    execute_command = "echo '${var.ssh_password}' | {{ .Vars }} sudo -S -E bash -eux '{{ .Path }}'"
    scripts = [
      "scripts/00-minimize-bootstrap.sh",
      "scripts/10-wait-cloud-init.sh"
    ]
  }

  provisioner "ansible" {
    playbook_file = "../ansible/playbooks/b2-smoke.yml"
    user          = var.ssh_username
    use_proxy     = false
    ansible_env_vars = [
      "ANSIBLE_HOST_KEY_CHECKING=False",
      "ANSIBLE_ROLES_PATH=/work/ansible/roles",
      "ANSIBLE_CONFIG=/work/ansible/ansible.cfg"
    ]
    extra_arguments = [
      "--become",
      "--become-user=root",
      "-e", "ansible_python_interpreter=/usr/bin/python3",
      "-e", "firewall_nftables_mode=bootstrap",
      "-e", "firewall_nftables_src_dir=/work/hardening/nftables"
    ]
  }

  provisioner "shell" {
    execute_command = "echo '${var.ssh_password}' | {{ .Vars }} sudo -S -E bash -eux '{{ .Path }}'"
    inline = [
      "junexis-cli version || true",
      "junexis-cli doctor --json || true",
      "test -f /var/lib/junexis/network_mode",
      "grep -q bootstrap /var/lib/junexis/network_mode",
      "command -v nft",
      "! dpkg -l | grep -qi thehive",
      "echo B2_SMOKE_GUEST_OK"
    ]
  }

  post-processor "manifest" {
    output     = "${var.output_directory}/packer-manifest.json"
    strip_path = true
  }
}
