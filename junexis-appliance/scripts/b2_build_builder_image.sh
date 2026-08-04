#!/usr/bin/env bash
# Build Docker image used for Packer+QEMU B2 builds (no host apt/sudo required)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${JUNEXIS_B2_BUILDER_IMAGE:-junexis-appliance-b2-builder:local}"

docker build -t "$IMAGE" -f "$ROOT/ci/Dockerfile.b2-builder" "$ROOT/ci"
echo "Built $IMAGE"
docker run --rm "$IMAGE" packer version
docker run --rm "$IMAGE" qemu-system-x86_64 --version | head -1
docker run --rm "$IMAGE" ansible-playbook --version | head -1
