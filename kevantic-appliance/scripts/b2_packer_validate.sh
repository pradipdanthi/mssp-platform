#!/usr/bin/env bash
# Packer validate + ansible syntax-check inside B2 builder image
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${KEVANTIC_B2_BUILDER_IMAGE:-kevantic-appliance-b2-builder:local}"

docker run --rm \
  -v "$ROOT:/work" \
  -w /work/packer \
  "$IMAGE" \
  bash -lc '
    set -euo pipefail
    packer init .
    packer validate -var-file=vars/b2-docker.pkrvars.hcl \
      -var "ubuntu_iso_url=file:///cache/ubuntu-24.04.4-live-server-amd64.iso" \
      -var "ubuntu_iso_checksum=sha256:e907d92eeec9df64163a7e454cbc8d7755e8ddc7ed42f99dbc80c40f1a138433" \
      .
    ANSIBLE_ROLES_PATH=/work/ansible/roles \
      ansible-playbook --syntax-check /work/ansible/playbooks/b2-smoke.yml
    ANSIBLE_ROLES_PATH=/work/ansible/roles \
      ansible-playbook --syntax-check /work/ansible/playbooks/site.yml
    echo B2_PACKER_VALIDATE_OK
  '
