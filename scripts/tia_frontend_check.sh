#!/usr/bin/env bash
# frontend-soc: type errors in the working tree vs the unchanged HEAD baseline, the bridge
# unit tests, and a production build. LOCAL evidence only. Nothing is deployed.
#
#   ./scripts/tia_frontend_check.sh
#
# A regression is an error that exists now and not at HEAD (compared by file + code + message,
# ignoring line numbers). Baseline errors are listed separately and are not hidden.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="$(mktemp -d /tmp/tia-fe-XXXXXX)"
trap 'docker run --rm -v "$W:/w" alpine rm -rf /w/base /w/now >/dev/null 2>&1; rm -rf "$W"' EXIT
mkdir -p "$W/base" "$W/now"
(cd "$ROOT" && git archive HEAD frontend-soc | tar -x -C "$W/base")
cp -r "$ROOT/frontend-soc" "$W/now/"
rm -rf "$W/now/frontend-soc/node_modules" "$W/now/frontend-soc/dist"

IMG=node:22-alpine
tsc_in() { # dir outfile
  docker run --rm -v "$1:/w" -w /w/frontend-soc $IMG sh -c \
    "npm install --no-audit --no-fund --silent >/dev/null 2>&1; npx tsc --noEmit -p . 2>&1" \
    | sed -E 's/\([0-9]+,[0-9]+\)//' | grep -E "error TS" | sort -u > "$2"
}
tsc_in "$W/base" "$W/base.txt"
tsc_in "$W/now" "$W/now.txt"
echo "type errors at HEAD baseline: $(wc -l < "$W/base.txt")   in working tree: $(wc -l < "$W/now.txt")"
reg="$(comm -13 "$W/base.txt" "$W/now.txt")"
fixed="$(comm -23 "$W/base.txt" "$W/now.txt")"
[[ -n "$fixed" ]] && { echo "--- errors present at HEAD and gone now:"; echo "$fixed"; }
fail=0
if [[ -n "$reg" ]]; then echo "--- REGRESSIONS (new type errors):"; echo "$reg"; fail=1; else echo "no new type errors versus the HEAD baseline"; fi

echo "--- bridge unit tests"
docker run --rm -v "$ROOT/frontend-soc:/w:ro" -w /w $IMG node --experimental-strip-types --test src/lib/uiBridge.test.ts src/lib/tiaEars.test.ts 2>&1 | grep -E "^# (tests|pass|fail)" || fail=1

echo "--- production build"
docker run --rm -v "$W/now:/w" -w /w/frontend-soc $IMG sh -c "npm install --no-audit --no-fund --silent >/dev/null 2>&1; npx vite build 2>&1 | tail -4" || fail=1
[[ $fail -eq 0 ]] && echo "FRONTEND CHECK: no gate failed (local evidence only)" || { echo "FRONTEND CHECK: FAILED"; exit 1; }
