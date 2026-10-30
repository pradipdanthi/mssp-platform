#!/usr/bin/env bash
# Create an internal CA and a server certificate for the SOC agent (authenticated TLS).
#
#   OUT=/etc/soc-agent/tls AGENT_NAMES="soc-agent.internal,192.168.0.228" ./scripts/tia_tls_setup.sh
#
# Output (OUT):
#   ca.crt      distribute to the control plane as SOC_AGENT_CA_BUNDLE (public, not secret)
#   agent.crt   agent server certificate (SAN = AGENT_NAMES)
#   agent.key   agent private key, mode 0640 root:soc-agent when run as root (never copy elsewhere)
#   ca.key      CA private key. Keep OFFLINE: the script writes it to $OUT/ca-private/ for you to move.
# Prints fingerprints only; never prints key material.
set -euo pipefail
OUT="${OUT:?set OUT to the output directory}"
NAMES="${AGENT_NAMES:?set AGENT_NAMES, comma separated DNS names and/or IPs the control plane will use}"
DAYS_CA="${DAYS_CA:-1825}"; DAYS_LEAF="${DAYS_LEAF:-397}"
umask 077
mkdir -p "$OUT" "$OUT/ca-private"
san=""; i=1; j=1
IFS=',' read -ra items <<<"$NAMES"
for n in "${items[@]}"; do
  n="${n// /}"
  if [[ "$n" =~ ^[0-9.]+$ || "$n" == *:* ]]; then san+="IP.$i=$n"$'\n'; i=$((i+1)); else san+="DNS.$j=$n"$'\n'; j=$((j+1)); fi
done
cfg="$(mktemp)"; trap 'rm -f "$cfg"' EXIT
cat >"$cfg" <<CFG
[req]
distinguished_name=dn
prompt=no
[dn]
CN=SOC agent
[v3]
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=@alt
[alt]
$san
CFG
if [[ ! -f "$OUT/ca.crt" ]]; then
  openssl genrsa -out "$OUT/ca-private/ca.key" 4096 2>/dev/null
  openssl req -x509 -new -key "$OUT/ca-private/ca.key" -sha256 -days "$DAYS_CA" -subj "/CN=Kevantic SOC internal CA" -out "$OUT/ca.crt"
fi
openssl genrsa -out "$OUT/agent.key" 3072 2>/dev/null
openssl req -new -key "$OUT/agent.key" -config "$cfg" -out "$OUT/agent.csr"
openssl x509 -req -in "$OUT/agent.csr" -CA "$OUT/ca.crt" -CAkey "$OUT/ca-private/ca.key" -CAcreateserial \
  -days "$DAYS_LEAF" -sha256 -extfile "$cfg" -extensions v3 -out "$OUT/agent.crt" 2>/dev/null
rm -f "$OUT/agent.csr" "$OUT/ca.srl"
chmod 644 "$OUT/ca.crt" "$OUT/agent.crt"; chmod 640 "$OUT/agent.key"
if [[ $EUID -eq 0 ]] && getent group soc-agent >/dev/null; then chgrp soc-agent "$OUT/agent.key"; fi
echo "CA fingerprint:    $(openssl x509 -in "$OUT/ca.crt" -noout -fingerprint -sha256)"
echo "Agent certificate: $(openssl x509 -in "$OUT/agent.crt" -noout -enddate)"
echo "Move $OUT/ca-private/ca.key offline. Set SOC_AGENT_URL=https://<name>:8443 and SOC_AGENT_CA_BUNDLE=<path to ca.crt> on the control plane."
