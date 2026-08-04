# junexis-cli (B1 — Python stub)

Specification: `../../docs/JUNEXIS_CLI_SPEC.md`  
Architecture: `docs/KB093_…` (bootstrap → lock; no TheHive; Appliance Mgmt separate server in production)

## Run from git tree

```bash
cd /opt/mssp-control/junexis-appliance/cli/junexis-cli
export PYTHONPATH=$PWD
export JUNEXIS_STATE_DIR=/tmp/junexis-state-demo
export JUNEXIS_CONFIG_DIR=/tmp/junexis-config-demo
python3 -m junexis_cli version
python3 -m junexis_cli setup --token "$TOKEN" --appliance-name DEMO --deploy-method customer-vm
python3 -m junexis_cli bootstrap update --dry-run
python3 -m junexis_cli network lock --yes --dry-run
python3 -m junexis_cli status --json
```

Or: `./junexis-cli …` (wrapper adds `PYTHONPATH`).

## Validate

```bash
cd /opt/mssp-control
./scripts/kb093b_validate_junexis_cli_b1.sh
```

## Layout

- `junexis_cli/cli.py` — argparse commands
- `junexis_cli/state.py` — `/var/lib/junexis` JSON state
- `junexis_cli/network.py` — apply `bootstrap.nft` / `locked.nft`
- `junexis_cli/bootstrap.py` — first-time critical OS/engine update window

Go rewrite remains optional later for a static binary on the minimal ISO.
