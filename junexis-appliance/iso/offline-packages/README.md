# Offline package pool (airgap ISO) — ALL catalogue engines

Populate with:

```bash
./junexis-appliance/scripts/b2_fetch_offline_packages.sh
```

## Contents

| Artifact | Services |
|----------|----------|
| `wazuh-manager_*.deb` + `fluent-bit_*.deb` | svc-01 (+ svc-05 SCA on Manager) |
| `suricata_*.deb` + deps | svc-06 NDR |
| `zeek-lts*.deb` / `zeekctl-lts*.deb` | svc-06 NDR |
| `bin/nuclei`, `bin/vuls` (+ optional `vuls-scanner`) | svc-04 VMaaS, svc-09 EASM |
| `python3-cryptography_*.deb`, pip/venv | license + CLI |
| `podman_*.deb` | container runtime |
| `wheels/duckdb*.whl` | local datalake / hunt (svc-07/08) |

Junexis-native workers (svc-02/03/07/08/10) install from payload source and
`/usr/bin/junexis-engine-worker` — no third-party .deb required.

Firstboot installs everything, then **disables** all catalogue units until
`junexis-cli license apply`.
