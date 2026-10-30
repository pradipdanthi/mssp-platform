#!/usr/bin/env bash
# Before relying on a rollback target, prove it understands the safe-mode flag.
#   ./scripts/tia_rollback_check.sh <git-ref>      e.g. HEAD, a release tag, a commit
#
# TIA_INVESTIGATION_MODE=manual_review only has an effect in code that reads it.
# A ref that does not contain it keeps the legacy behaviour (heuristic fallback
# verdicts) no matter what the environment says, so this script refuses to call
# such a ref a safe rollback target.
set -euo pipefail
REF="${1:?usage: tia_rollback_check.sh <git-ref>}"
cd "$(dirname "$0")/.."
git rev-parse --verify --quiet "$REF^{commit}" >/dev/null || { echo "unknown ref: $REF" >&2; exit 2; }

reads_flag=0; legacy_fallback=0
git grep -q "TIA_INVESTIGATION_MODE" "$REF" -- backend-api/app/services/tia_investigation.py 2>/dev/null && reads_flag=1
git grep -q "heuristic_fallback_cursor_error" "$REF" -- soc-agent/app 2>/dev/null && legacy_fallback=1

echo "ref: $REF ($(git rev-parse --short "$REF"))"
echo "  backend reads TIA_INVESTIGATION_MODE: $([[ $reads_flag == 1 ]] && echo yes || echo NO)"
echo "  agent still contains heuristic_fallback_cursor_error: $([[ $legacy_fallback == 1 ]] && echo YES || echo no)"
if [[ $reads_flag == 1 && $legacy_fallback == 0 ]]; then
  echo "RESULT: SAFE — this ref honours manual_review and cannot manufacture a benign verdict from a failed call."
  exit 0
fi
echo "RESULT: NOT SAFE — rolling back to this ref re-enables the false-benign path, and TIA_INVESTIGATION_MODE=manual_review will be ignored."
echo "  If you must run this ref, disable the pipeline instead (SOC_AGENT_ENABLED=false and AI_DEEP_TRIAGE_ENABLED=false):"
echo "  alerts stay visible and untouched, but nothing is triaged or paged automatically. Staff must watch the queue."
exit 1
