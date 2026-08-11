#!/usr/bin/env bash
# convert_verity.sh — Post-process Packer raw disk into dm-verity + UKI
# Required env:
#   MSSP_RAW_DISK   Absolute path to the Packer-produced raw disk image
#   MSSP_OUTPUT_DIR Directory for artifacts (root hash, cmdline, UKI)
#   MSSP_UKI_OUT    Destination path for mssp-appliance-uki.efi (optional)
#
# Host prerequisites: losetup, parted/sfdisk, mount, veritysetup (cryptsetup),
# systemd-ukify (or ukify), qemu-nbd optional fallback, root privileges.

set -euo pipefail

log() { printf '[convert_verity] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

for c in losetup sgdisk blkid mount umount veritysetup findmnt sync; do
  need_cmd "$c"
done

if command -v systemd-ukify >/dev/null 2>&1; then
  UKIFY=(systemd-ukify)
elif command -v ukify >/dev/null 2>&1; then
  UKIFY=(ukify)
else
  die "neither systemd-ukify nor ukify found — install systemd-ukify"
fi

[[ "$(id -u)" -eq 0 ]] || die "must run as root (losetup + mount + veritysetup)"

RAW="${MSSP_RAW_DISK:-}"
OUT_DIR="${MSSP_OUTPUT_DIR:-}"
UKI_OUT="${MSSP_UKI_OUT:-${OUT_DIR}/mssp-appliance-uki.efi}"

[[ -n "$RAW" && -f "$RAW" ]] || die "MSSP_RAW_DISK not set or not a file: ${RAW:-<empty>}"
[[ -n "$OUT_DIR" ]] || die "MSSP_OUTPUT_DIR not set"
mkdir -p "$OUT_DIR"

WORK="$(mktemp -d /tmp/mssp-verity.XXXXXX)"
LOOP=""
ROOT_PART=""
BOOT_MNT=""
ROOT_MNT=""
HASH_IMG=""
cleanup() {
  set +e
  if [[ -n "$BOOT_MNT" && -d "$BOOT_MNT" ]]; then
    umount -R "$BOOT_MNT" 2>/dev/null || true
  fi
  if [[ -n "$ROOT_MNT" && -d "$ROOT_MNT" ]]; then
    umount -R "$ROOT_MNT" 2>/dev/null || true
  fi
  if [[ -n "$LOOP" ]]; then
    losetup -d "$LOOP" 2>/dev/null || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

log "Attaching raw disk: $RAW"
LOOP="$(losetup --find --show --partscan "$RAW")"
[[ -n "$LOOP" ]] || die "losetup failed"
log "Loop device: $LOOP"
sleep 1
# Ensure partition nodes exist
partprobe "$LOOP" 2>/dev/null || true
udevadm settle 2>/dev/null || sleep 2

# Discover partitions: prefer largest ext4 as root, FAT as ESP, second ext4 as /boot
mapfile -t PARTS < <(lsblk -lnpo NAME,FSTYPE,TYPE,SIZE "$LOOP" | awk '$3=="part"{print}')
[[ ${#PARTS[@]} -ge 1 ]] || die "no partitions found on $LOOP"

ROOT_PART=""
BOOT_PART=""
ESP_PART=""
declare -A PART_SIZE

while read -r name fstype _ptype size; do
  PART_SIZE["$name"]="$size"
  case "${fstype:-}" in
    vfat|fat32|FAT32)
      ESP_PART="$name"
      ;;
    ext4)
      if [[ -z "$BOOT_PART" ]]; then
        BOOT_PART="$name"
      else
        # Prefer larger ext4 as root
        if [[ -z "$ROOT_PART" ]]; then
          ROOT_PART="$name"
        else
          # keep largest as root
          :
        fi
      fi
      ;;
  esac
done < <(lsblk -lnpo NAME,FSTYPE,TYPE,SIZE "$LOOP" | awk '$3=="part"{print $1,$2,$3,$4}')

# Re-scan: pick largest ext4 as root, remaining ext4 as boot
mapfile -t EXT4S < <(lsblk -lnpo NAME,FSTYPE,SIZE -b "$LOOP" | awk '$2=="ext4"{print $1,$3}' | sort -k2 -n)
if [[ ${#EXT4S[@]} -eq 0 ]]; then
  die "no ext4 partitions found — cannot locate root filesystem"
fi
# last (largest) is root; if two+, first is boot
ROOT_PART="$(echo "${EXT4S[-1]}" | awk '{print $1}')"
if [[ ${#EXT4S[@]} -ge 2 ]]; then
  BOOT_PART="$(echo "${EXT4S[0]}" | awk '{print $1}')"
fi
if [[ -z "${ESP_PART:-}" ]]; then
  ESP_PART="$(lsblk -lnpo NAME,FSTYPE "$LOOP" | awk '$2 ~ /vfat|fat/ {print $1; exit}')"
fi

[[ -n "$ROOT_PART" ]] || die "failed to identify root partition"
log "Root partition: $ROOT_PART"
log "Boot partition: ${BOOT_PART:-<none>}"
log "ESP partition:  ${ESP_PART:-<none>}"

ROOT_MNT="$WORK/root"
BOOT_MNT="$WORK/boot"
mkdir -p "$ROOT_MNT" "$BOOT_MNT"

# Mount boot volume to harvest vmlinuz + initrd (prefer /boot partition, else root's /boot)
KERNEL=""
INITRD=""
STUB=""

if [[ -n "${BOOT_PART:-}" ]]; then
  mount -o ro "$BOOT_PART" "$BOOT_MNT"
  if [[ -n "${ESP_PART:-}" ]]; then
    mkdir -p "$BOOT_MNT/efi"
    mount -o ro "$ESP_PART" "$BOOT_MNT/efi" 2>/dev/null || true
  fi
  KERNEL="$(find "$BOOT_MNT" -type f \( -name 'vmlinuz*' -o -name 'vmlinux*' \) ! -name '*.old' | sort | tail -1 || true)"
  INITRD="$(find "$BOOT_MNT" -type f \( -name 'initrd.img*' -o -name 'initramfs*' \) ! -name '*.old' | sort | tail -1 || true)"
fi

if [[ -z "$KERNEL" || -z "$INITRD" ]]; then
  mount -o ro "$ROOT_PART" "$ROOT_MNT"
  KERNEL="$(find "$ROOT_MNT/boot" -type f -name 'vmlinuz*' ! -name '*.old' 2>/dev/null | sort | tail -1 || true)"
  INITRD="$(find "$ROOT_MNT/boot" -type f -name 'initrd.img*' ! -name '*.old' 2>/dev/null | sort | tail -1 || true)"
  if [[ -z "$KERNEL" || -z "$INITRD" ]]; then
    die "could not locate vmlinuz/initrd on boot or root partitions"
  fi
fi

# Locate systemd EFI stub
for candidate in \
  /usr/lib/systemd/boot/efi/linuxx64.efi.stub \
  /usr/lib/systemd/boot/efi/linuxia32.efi.stub \
  /lib/systemd/boot/efi/linuxx64.efi.stub \
  "$BOOT_MNT/efi/EFI/systemd/systemd-bootx64.efi"
do
  if [[ -f "$candidate" ]]; then
    STUB="$candidate"
    break
  fi
done
[[ -n "$STUB" ]] || die "systemd EFI stub not found on build host — install systemd-boot-efi"

log "Kernel: $KERNEL"
log "Initrd: $INITRD"
log "Stub:   $STUB"

# Unmount root if mounted read-only before formatting verity (veritysetup needs exclusive access)
if findmnt "$ROOT_MNT" >/dev/null 2>&1; then
  umount -R "$ROOT_MNT"
fi

HASH_IMG="$OUT_DIR/mssp-root.hash"
ROOT_UUID="$(blkid -s UUID -o value "$ROOT_PART" || true)"
ROOT_DEV_BASENAME="$(basename "$ROOT_PART")"

log "Formatting dm-verity hash tree for $ROOT_PART → $HASH_IMG"
# veritysetup format prints Root hash on stderr/stdout
VERITY_OUT="$(veritysetup format "$ROOT_PART" "$HASH_IMG" --hash=sha256 --data-block-size=4096 --hash-block-size=4096 2>&1)"
printf '%s\n' "$VERITY_OUT" | tee "$OUT_DIR/veritysetup-format.log"

ROOT_HASH="$(printf '%s\n' "$VERITY_OUT" | awk -F': ' '/Root hash:/ {print $2}' | tr -d '[:space:]')"
[[ -n "$ROOT_HASH" && ${#ROOT_HASH} -eq 64 ]] || die "failed to parse Root hash from veritysetup output"

printf '%s\n' "$ROOT_HASH" > "$OUT_DIR/root-hash.txt"
log "Root hash: $ROOT_HASH"

# Build dm-mod.create / verity cmdline for early boot.
# Device mapper name: mssp-verity-root
# Data device will be the root partition by PARTUUID when available.
PARTUUID="$(blkid -s PARTUUID -o value "$ROOT_PART" || true)"
if [[ -n "$PARTUUID" ]]; then
  DATA_SPEC="PARTUUID=${PARTUUID}"
else
  DATA_SPEC="/dev/disk/by-uuid/${ROOT_UUID}"
fi

# Hash device is shipped alongside the image; operators map it as a second volume or
# embed it in a dedicated partition. For UKI boot we reference a well-known path that
# initramfs hooks (or hypervisor) expose as /dev/mapper/mssp-hash or a loop-backed file.
HASH_PARTUUID_FILE="$OUT_DIR/hash-device.note"
cat > "$HASH_PARTUUID_FILE" <<EOF
Place or attach ${HASH_IMG} as a block device at boot.
Recommended: second GPT partition or qemu -drive file=${HASH_IMG}
Initramfs must expose it as /dev/mapper/mssp-hash-src (or update dm-mod.create).
EOF

# Kernel cmdline: verity-protected read-only root
CMDLINE=$(cat <<EOF
console=tty0 console=ttyS0,115200n8 quiet splash
ro
root=/dev/mapper/mssp-verity-root
dm-mod.create="mssp-verity-root,0,,ro,0 verity 1 ${DATA_SPEC} HASHDEV 4096 4096 DATA_BLOCKS HASH_START sha256 ${ROOT_HASH} HASH_SALT"
systemd.verity=1
rd.live.overlay.overlayfs=1
EOF
)

# Fill DATA_BLOCKS / HASH_START / HASH_SALT from veritysetup verbose fields when present
DATA_BLOCKS="$(printf '%s\n' "$VERITY_OUT" | awk -F': ' '/Data blocks:/ {print $2}' | tr -d '[:space:]')"
HASH_OFFSET="$(printf '%s\n' "$VERITY_OUT" | awk -F': ' '/Hash offset:/ {print $2}' | tr -d '[:space:]')"
SALT="$(printf '%s\n' "$VERITY_OUT" | awk -F': ' '/Salt:/ {print $2}' | tr -d '[:space:]')"
[[ -n "$DATA_BLOCKS" ]] || DATA_BLOCKS="0"
[[ -n "$HASH_OFFSET" ]] || HASH_OFFSET="0"
[[ -n "$SALT" ]] || SALT="-"

# Produce a concrete dm-mod.create line (HASHDEV placeholder documented for initramfs)
DM_CREATE="mssp-verity-root,,,ro,0 verity 1 ${DATA_SPEC} /dev/mapper/mssp-hash-src 4096 4096 ${DATA_BLOCKS} ${HASH_OFFSET} sha256 ${ROOT_HASH} ${SALT}"

CMDLINE_FINAL="console=tty0 console=ttyS0,115200n8 ro root=/dev/mapper/mssp-verity-root dm-mod.create=\"${DM_CREATE}\" systemd.verity_root_data=${DATA_SPEC} systemd.verity_root_hash=${ROOT_HASH} systemd.verity_root_options=restart-on-corruption"

printf '%s\n' "$CMDLINE_FINAL" > "$OUT_DIR/kernel-cmdline.txt"
log "Wrote kernel cmdline → $OUT_DIR/kernel-cmdline.txt"

log "Assembling Unified Kernel Image → $UKI_OUT"
"${UKIFY[@]}" build \
  --linux="$KERNEL" \
  --initrd="$INITRD" \
  --cmdline="$CMDLINE_FINAL" \
  --os-release="@/etc/os-release" \
  --uname="$(uname -r)" \
  --stub="$STUB" \
  --output="$UKI_OUT"

[[ -f "$UKI_OUT" ]] || die "UKI was not produced at $UKI_OUT"
sha256sum "$UKI_OUT" | tee "$OUT_DIR/mssp-appliance-uki.efi.sha256"
sha256sum "$HASH_IMG" | tee "$OUT_DIR/mssp-root.hash.sha256"
sha256sum "$RAW" | tee "$OUT_DIR/raw-disk.sha256"

# Manifest for operators / CI
cat > "$OUT_DIR/mssp-verity-manifest.json" <<EOF
{
  "raw_disk": "$(basename "$RAW")",
  "root_partition": "$ROOT_PART",
  "root_partuuid": "${PARTUUID:-}",
  "root_uuid": "${ROOT_UUID:-}",
  "root_hash_sha256": "$ROOT_HASH",
  "hash_tree": "$(basename "$HASH_IMG")",
  "data_blocks": "$DATA_BLOCKS",
  "hash_offset": "$HASH_OFFSET",
  "salt": "$SALT",
  "uki": "$(basename "$UKI_OUT")",
  "cmdline_file": "kernel-cmdline.txt",
  "dm_mod_create": "$DM_CREATE"
}
EOF

log "SUCCESS"
log "  UKI:        $UKI_OUT"
log "  Hash tree:  $HASH_IMG"
log "  Root hash:  $ROOT_HASH"
log "  Manifest:   $OUT_DIR/mssp-verity-manifest.json"
exit 0
