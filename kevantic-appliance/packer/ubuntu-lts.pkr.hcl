# Kevantic Appliance — Ubuntu Server 24.04 LTS Packer (B2)
# Build inside ci/Dockerfile.b2-builder (qemu + packer) — do not run minimize on mssp-control.

packer {
  required_version = ">= 1.9.0"
  required_plugins {
    qemu = {
      version = "= 1.1.3"
      source  = "github.com/hashicorp/qemu"
    }
    ansible = {
      version = "= 1.1.3"
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
  default = "kevantic"
}

variable "ssh_password" {
  type      = string
  default   = "KevanticBuildOnlyChangeMe"
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
  default = "output-kevantic-appliance"
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

  # Seed ISO is more reliable than nocloud-net HTTP for Subiquity autoinstall.
  # Live installer may open SSH early with unrelated credentials; Packer must not
  # abort on those auth failures before the installed system reboots.
  cd_files = [
    "./http/meta-data",
    "./http/user-data"
  ]
  cd_label = "cidata"

  http_directory = "http"
  http_port_min  = 8200
  http_port_max  = 8299

  ssh_username     = var.ssh_username
  ssh_password     = var.ssh_password
  ssh_private_key_file = "/work/.tools/build-ssh/kevantic_packer"
  ssh_clear_authorized_keys = false
  ssh_timeout      = "60m"
  # Live-ISO SSH rejects our key/password every few seconds; 100 ≈ 17m abort.
  ssh_handshake_attempts = 1200

  boot_wait = "8s"
  boot_command = [
    "e<wait>",
    "<down><down><down><end>",
    # cloud-init finds the Packer-generated volume labeled cidata
    " autoinstall ds=nocloud ---",
    "<f10>"
  ]

  vm_name = "kevantic-appliance-${var.appliance_version}"
}

build {
  name    = "kevantic-appliance"
  sources = ["source.qemu.ubuntu_lts"]

  provisioner "shell" {
    execute_command = "echo '${var.ssh_password}' | {{ .Vars }} sudo -S -E bash -eux '{{ .Path }}'"
    scripts = [
      "scripts/10-wait-cloud-init.sh",
      "scripts/00-minimize-bootstrap.sh"
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
      "kevantic-cli version || true",
      "kevantic-cli doctor --json || true",
      "test -f /var/lib/kevantic/network_mode",
      "grep -q bootstrap /var/lib/kevantic/network_mode",
      "command -v nft",
      "test -d /opt/kevantic/appliance-src/appliance/datalake",
      "test -d /var/log/kevantic/datalake",
      "export PYTHONPATH=/opt/kevantic/appliance-src; python3 -c 'from appliance.datalake import DataLakeArchiver; print(DataLakeArchiver)'",
      "! dpkg -l | grep -qi thehive",
      "echo B2_SMOKE_GUEST_OK"
    ]
  }

  post-processor "manifest" {
    output     = "${var.output_directory}/packer-manifest.json"
    strip_path = true
  }
}
