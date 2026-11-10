#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track implicit-behaviours_20261109 (gluon PLAN.md RUST-1.9): every
# check docs/implicit-behaviours.md names exists; with --run, they all pass
# against the Rust build (the CDC and probe items need the CDC jars).
#   scripts/verify-implicit-behaviours.sh [--run]
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
. "$(dirname "$SELF")/lib/owner.sh"
run_as_owner "$PWD" "$SELF" "$@"
passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
RUST_REPO="$(realpath ../../services/user-service-rs)"

echo "== 1. Every check the list names exists =="
ids=()
while read -r ref; do
  file="${ref%%::*}"
  name="${ref##*::}"
  path="checks/$file"
  [ -f "$path" ] || path="$file"
  if grep -q "^def $name(" "$path" 2> /dev/null; then
    ok "$ref"
    ids+=("$path::$name")
  else
    bad "$ref: no such check"
  fi
done < <(grep -oE '`[a-z_/]+\.py::test_[a-z0-9_]+`' docs/implicit-behaviours.md | tr -d '`' | sort -u)

if [ "${1:-}" = "--run" ]; then
  echo "== 2. They pass against the Rust build =="
  (cd "$RUST_REPO" && cargo build -q --locked -p user-service -p events-probe && scripts/asyncapi-html.sh > /dev/null) \
    || bad "building the Rust service and its AsyncAPI HTML failed"
  log="$(mktemp)"
  uv run --no-sync pytest "${ids[@]}" -p no:cacheprovider -rA --tb=line -q \
    --target-cmd "$RUST_REPO/target/debug/user-service" --target-cwd "$RUST_REPO" \
    --probe-cmd "$RUST_REPO/target/debug/events-probe" > "$log" 2>&1
  while read -r outcome test rest; do
    if [ "$outcome" = PASSED ]; then ok "${test##*::}"; else bad "${test##*::} $rest"; fi
  done < <(grep -E '^(PASSED|FAILED|ERROR) [^ ]+::' "$log")
  rm -f "$log"
fi

echo
if [ "$failed" = 0 ]; then
  echo "PASS: implicit behaviours verified ($passed checks)"
else
  echo "FAIL: $failed of $((passed + failed)) checks failed"
  exit 1
fi
