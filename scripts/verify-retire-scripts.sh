#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track retire-scripts_20261113 (gluon TD-46, TD-41): the track scripts
# CI and bin/verify-port already cover are gone, nothing live still names them,
# the kept ones parse, verify-check-group.sh only runs a group against a build
# (its source check is CI's now), and workflow.md states the retirement rule.
# Retired itself when the track is archived. Each result is printed as found.
#   scripts/verify-retire-scripts.sh [--skip-ci]
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
. "$(dirname "$SELF")/lib/owner.sh"
run_as_owner "$PWD" "$SELF" "$@"
passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
SCRATCH="$(mktemp -d /tmp/verify-retire-scripts.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

RETIRED=(cdc-group docs-group outbox-group rest-group schema-group telemetry-groups
  probe-group probe-stubs isolated-runner multi-service-harness portable-harness
  notification-capture notification-rest-group implicit-behaviours)
KEPT=(verify-check-group verify-user-scala-confirmation verify-cluster-mode ci)

echo "== 1. CI (scripts/ci.sh) =="
if [ "${1:-}" = "--skip-ci" ]; then
  echo "skip --skip-ci given"
elif scripts/ci.sh > "$SCRATCH/ci.log" 2>&1; then
  ok "$(grep -Eo '[0-9]+ passed' "$SCRATCH/ci.log" | tail -1), $(grep -Eo 'Total coverage: [0-9.]+%' "$SCRATCH/ci.log")"
else
  bad "scripts/ci.sh failed"
  tail -8 "$SCRATCH/ci.log" | sed 's/^/     /'
fi

echo "== 2. Retired scripts are gone =="
for name in "${RETIRED[@]}"; do
  if [ -e "scripts/verify-$name.sh" ]; then bad "scripts/verify-$name.sh still exists"; else ok "verify-$name.sh gone"; fi
done

echo "== 3. Nothing live names them (conductor/archive is history) =="
for name in "${RETIRED[@]}"; do
  hits="$(git grep -l "verify-$name\.sh" -- . ':!conductor/archive' ':!conductor/tracks/retire-scripts_*' ':!scripts/verify-retire-scripts.sh')"
  if [ -z "$hits" ]; then ok "verify-$name.sh: no live references"; else bad "verify-$name.sh named in: $(echo $hits)"; fi
done

echo "== 4. Kept scripts =="
for name in "${KEPT[@]}"; do
  if [ -f "scripts/$name.sh" ] && bash -n "scripts/$name.sh"; then
    ok "scripts/$name.sh present, parses"
  else
    bad "scripts/$name.sh missing or does not parse"
  fi
done

echo "== 5. verify-check-group.sh runs a group, nothing else =="
for text in 'scripts/ci.sh' 'Source:' '--skip-ci'; do
  if grep -qF -- "$text" scripts/verify-check-group.sh; then
    bad "verify-check-group.sh still mentions $text"
  else
    ok "verify-check-group.sh: no $text"
  fi
done
if [ -f tests/unit/test_check_sources.py ]; then
  ok "the source check is CI's: tests/unit/test_check_sources.py"
else
  bad "no tests/unit/test_check_sources.py"
fi

echo "== 6. workflow.md states the rule =="
rule="$(sed -n '/^### Phase Completion/,/^### /p' conductor/workflow.md | grep -m1 'Retiring the script')"
if [ -n "$rule" ]; then ok "Phase Completion: ${rule:0:110}…"; else bad "Phase Completion has no 'Retiring the script' rule"; fi

echo
if [ "$failed" = 0 ]; then
  echo "PASS: retire-scripts verified ($passed checks)"
else
  echo "FAIL: $failed of $((passed + failed)) checks failed"
  exit 1
fi
