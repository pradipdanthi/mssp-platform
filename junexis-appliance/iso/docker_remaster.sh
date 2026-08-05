#!/usr/bin/env bash
# Runs inside builder container: extract Ubuntu live ISO, inject nocloud + payload, rebuild.
set -euo pipefail

ISO_IN="${1:-/in.iso}"
WORK="${2:-/work}"
SRC="$WORK/source-iso"
DST="$WORK/new-iso"
OUT="$WORK/Junexis-Appliance-Install.iso"

rm -rf "$SRC" "$DST" "$OUT"
mkdir -p "$SRC" "$DST"

echo "Extracting $ISO_IN ..."
xorriso -osirrox on -indev "$ISO_IN" -extract / "$SRC"
# Prefer cp over rsync (builder image may not include rsync)
cp -a "$SRC"/. "$DST"/

mkdir -p "$DST/nocloud" "$DST/junexis-payload"
cp -a "$WORK/seed/user-data" "$WORK/seed/meta-data" "$DST/nocloud/"
cp -a "$WORK/seed/junexis-payload/." "$DST/junexis-payload/"

AUTO_ARGS='autoinstall ds=nocloud\;s=/cdrom/nocloud/'

# Replace Ubuntu branding with a single Junexis unattended entry.
# (Without source.id in user-data, Subiquity used to ask Server vs Minimized.)
while IFS= read -r -d '' grub; do
  cat >"$grub" <<'GRUB'
set timeout=5
set default=0

loadfont unicode

set menu_color_normal=white/black
set menu_color_highlight=black/light-gray

menuentry "Install Junexis Appliance (automatic — do not pick other options)" {
	set gfxpayload=keep
	linux	/casper/vmlinuz autoinstall ds=nocloud\;s=/cdrom/nocloud/ ---
	initrd	/casper/initrd
}
grub_platform
if [ "$grub_platform" = "efi" ]; then
menuentry "UEFI Firmware Settings" {
	fwsetup
}
fi
GRUB
done < <(find "$DST" -name 'grub.cfg' -print0 2>/dev/null)

# Patch isolinux / BIOS text menus similarly when present
while IFS= read -r -d '' cfg; do
  sed -i "s|Try or Install Ubuntu Server|Install Junexis Appliance (automatic)|g" "$cfg" || true
  sed -i "s| ---| ${AUTO_ARGS} ---|g" "$cfg" || true
done < <(find "$DST" \( -name 'txt.cfg' -o -name 'isolinux.cfg' \) -print0 2>/dev/null)

echo "Building hybrid ISO ..."
# Prefer Ubuntu-style hybrid layout when eltorito image exists
ELT="$DST/boot/grub/i386-pc/eltorito.img"
EFI_IMG=""
if [[ -f "$DST/boot/grub/efi.img" ]]; then
  EFI_IMG="$DST/boot/grub/efi.img"
elif [[ -f "$DST/EFI/boot/bootx64.efi" ]]; then
  # Some ISOs ship bare EFI; create a small ESP image if missing
  EFI_IMG=""
fi

if [[ -f "$ELT" && -n "$EFI_IMG" ]]; then
  xorriso -as mkisofs \
    -r -V 'JUNEXIS_INSTALL' \
    -o "$OUT" \
    -J -joliet-long \
    -b boot/grub/i386-pc/eltorito.img \
    -c boot.catalog \
    -no-emul-boot -boot-load-size 4 -boot-info-table \
    -eltorito-alt-boot \
    -e boot/grub/efi.img -no-emul-boot \
    -isohybrid-gpt-basdat \
    "$DST"
elif [[ -f "$ELT" ]]; then
  xorriso -as mkisofs \
    -r -V 'JUNEXIS_INSTALL' \
    -o "$OUT" \
    -J -joliet-long \
    -b boot/grub/i386-pc/eltorito.img \
    -c boot.catalog \
    -no-emul-boot -boot-load-size 4 -boot-info-table \
    -eltorito-alt-boot \
    -e EFI/boot/bootx64.efi -no-emul-boot \
    "$DST" || xorriso -as mkisofs -r -V 'JUNEXIS_INSTALL' -J -joliet-long -o "$OUT" "$DST"
else
  xorriso -as mkisofs -r -V 'JUNEXIS_INSTALL' -J -joliet-long -o "$OUT" "$DST"
fi

ls -lh "$OUT"
echo "REMASTER_OK $OUT"
