# kevantic-cli (B1 — Python stub)

Specification: `../../docs/KEVANTIC_CLI_SPEC.md`  
Architecture: `docs/KB093_…` (bootstrap → lock; no TheHive; Appliance Mgmt separate server in production)

## Run from git tree

```bash
cd /opt/mssp-control/kevantic-appliance/cli/kevantic-cli
export PYTHONPATH=$PWD
export KEVANTIC_STATE_DIR=/tmp/kevantic-state-demo
export KEVANTIC_CONFIG_DIR=/tmp/kevantic-config-demo
python3 -m kevantic_cli version
python3 -m kevantic_cli setup --token "$TOKEN" --appliance-name DEMO --deploy-method customer-vm
python3 -m kevantic_cli bootstrap update --dry-run
python3 -m kevantic_cli network lock --yes --dry-run
python3 -m kevantic_cli status --json
```

Or: `./kevantic-cli …` (wrapper adds `PYTHONPATH`).

## Validate

```bash
cd /opt/mssp-control
./scripts/kb093b_validate_kevantic_cli_b1.sh
```

## Layout

- `kevantic_cli/cli.py` — argparse commands
- `kevantic_cli/state.py` — `/var/lib/kevantic` JSON state
- `kevantic_cli/network.py` — apply `bootstrap.nft` / `locked.nft`
- `kevantic_cli/bootstrap.py` — first-time critical OS/engine update window

Go rewrite remains optional later for a static binary on the minimal ISO.
