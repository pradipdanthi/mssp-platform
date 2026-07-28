#!/usr/bin/env bash
# KB-079: Run Nuclei + Vuls pullers (VM 109 scanners → control plane).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/kb079_pull_nuclei_findings.sh"
"$DIR/kb079_pull_vuls_findings.sh"
echo "KB-079 combined vuln scan sync finished."
