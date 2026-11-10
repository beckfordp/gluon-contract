#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track probe-group_20261109 (gluon PLAN.md RUST-6.5): CI, every probe
# check names its source, and the group runs green against the Rust
# events-probe (built here). Needs the CDC jars for the broker.
#   scripts/verify-probe-group.sh [--skip-ci]
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
owner="$(stat -c %U .)"
if [ "$(id -un)" != "$owner" ]; then
  if [ "$(id -u)" = 0 ] && command -v runuser > /dev/null; then
    echo "== re-running as $owner (the repo's owner) =="
    exec runuser -u "$owner" -- env HOME="$(getent passwd "$owner" | cut -d: -f6)" PATH="$PATH" \
      LANG=C.UTF-8 bash "$SELF" "$@"
  fi
  echo "FAIL run as $owner"
  exit 1
fi
passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
SCRATCH="$(mktemp -d /tmp/verify-probe-group.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT
RUST_REPO="$(realpath ../../services/user-service-rs)"

echo "== 1. CI (scripts/ci.sh) =="
if [ "${1:-}" = "--skip-ci" ]; then
  echo "skip --skip-ci given"
elif scripts/ci.sh > "$SCRATCH/ci.log" 2>&1; then
  ok "$(grep -Eo '[0-9]+ passed' "$SCRATCH/ci.log" | tail -1), $(grep -Eo 'Total coverage: [0-9.]+%' "$SCRATCH/ci.log")"
else
  bad "scripts/ci.sh failed"
  tail -8 "$SCRATCH/ci.log" | sed 's/^/     /'
fi

echo "== 2. Every probe check names its source =="
missing="$(grep -c 'Source:' checks/test_probe.py)"
checks="$(grep -c '^def test_' checks/test_probe.py)"
if [ "$missing" -ge "$checks" ]; then ok "$checks checks, each with a Source: line"; else bad "$checks checks but $missing Source: lines"; fi

echo "== 3. The group against the Rust events-probe =="
if (cd "$RUST_REPO" && cargo build -q --locked -p events-probe) > "$SCRATCH/build.log" 2>&1; then
  ok "built $RUST_REPO/target/debug/events-probe"
else
  bad "cargo build failed"
  tail -5 "$SCRATCH/build.log" | sed 's/^/     /'
fi
uv run --no-sync pytest checks/test_probe.py -p no:cacheprovider -rA --tb=line -q \
  --probe-cmd "$RUST_REPO/target/debug/events-probe" > "$SCRATCH/run.log" 2>&1
count=0
while read -r outcome test rest; do
  count=$((count + 1))
  if [ "$outcome" = PASSED ]; then ok "${test##*::}"; else bad "${test##*::} $rest"; fi
done < <(grep -E '^(PASSED|FAILED|ERROR) [^ ]+::' "$SCRATCH/run.log")
[ "$count" -gt 0 ] || bad "no probe checks ran"

echo
if [ "$failed" = 0 ]; then
  echo "PASS: probe group verified ($passed checks)"
else
  echo "FAIL: $failed of $((passed + failed)) checks failed"
  exit 1
fi
