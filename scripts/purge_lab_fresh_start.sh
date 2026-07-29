#!/usr/bin/env bash
# Full lab reset: MSSP database + Wazuh/TheHive/Redis + forensic files.
# Keeps platform_admin / soc_manager / soc_analyst and infra Wazuh agents 000/002.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 "$ROOT/scripts/purge_test_data.py" --via-docker --yes --engines
