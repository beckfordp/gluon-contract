#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track probe-stubs_20261109 (gluon PLAN.md RUST-6.1): the lookup stub
# and the restartable Kafka broker the probe group uses, through their tests
# (run here by name, each result printed as found), plus CI.
#   scripts/verify-probe-stubs.sh [--skip-ci]
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
SCRATCH="$(mktemp -d /tmp/verify-probe-stubs.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

echo "== 1. CI (scripts/ci.sh) =="
if [ "${1:-}" = "--skip-ci" ]; then
  echo "skip --skip-ci given"
elif scripts/ci.sh > "$SCRATCH/ci.log" 2>&1; then
  ok "$(grep -Eo '[0-9]+ passed' "$SCRATCH/ci.log" | tail -1), $(grep -Eo 'Total coverage: [0-9.]+%' "$SCRATCH/ci.log")"
else
  bad "scripts/ci.sh failed"
  tail -8 "$SCRATCH/ci.log" | sed 's/^/     /'
fi

echo "== 2. The lookup stub and the broker =="
uv run --no-sync pytest -p no:cacheprovider -rA -q tests/unit/test_http_stub.py \
  tests/integration/test_kafka_broker.py > "$SCRATCH/run.log" 2>&1
while read -r outcome test _; do
  if [ "$outcome" = PASSED ]; then ok "${test##*::}"; else bad "${test##*::} ($outcome)"; fi
done < <(grep -E '^(PASSED|FAILED|ERROR|SKIPPED) [^ ]+::' "$SCRATCH/run.log")

echo
if [ "$failed" = 0 ] && [ "$passed" -gt 0 ]; then
  echo "PASS: RUST-6.1 probe stubs verified ($passed checks)"
else
  echo "FAIL: $failed of $((passed + failed)) checks failed"
  exit 1
fi
