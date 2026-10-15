#!/bin/sh
# Proxmox hookscript for VM 105 (mirror source) and VM 106 (Suricata sensor).
# Proxmox recreates tap devices on every VM start, dropping the tc mirror that feeds
# the NDR sensor. Re-apply it on post-start of either VM.
#
# Install on the Proxmox host:
#   pvesm set local --content iso,vztmpl,backup,import,snippets
#   install -m 755 mssp-ndr-mirror-hook.sh /var/lib/vz/snippets/
#   install -m 755 mssp-kb043-mirror-vm105-to-106.sh /usr/local/sbin/
#   qm set 105 --hookscript local:snippets/mssp-ndr-mirror-hook.sh
#   qm set 106 --hookscript local:snippets/mssp-ndr-mirror-hook.sh

vmid="$1"
phase="$2"
MIRROR=/usr/local/sbin/mssp-kb043-mirror-vm105-to-106.sh

if [ "$phase" = "post-start" ]; then
    # Taps can lag the post-start event briefly; the other VM may also be down.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if "$MIRROR" enable >/dev/null 2>&1; then
            logger -t mssp-ndr-mirror "VM $vmid post-start: mirror tap105i0 -> tap106i1 enabled"
            exit 0
        fi
        sleep 2
    done
    logger -t mssp-ndr-mirror "VM $vmid post-start: mirror not enabled (peer VM down?)"
fi
exit 0
