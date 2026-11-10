#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies one check group (gluon PLAN.md RUST-1.3 onwards): CI green, every
# check names its source and every capture file it cites exists, and the group
# runs against the Rust build, each check's outcome reported as it is found.
#
#   scripts/verify-check-group.sh checks/test_<group>.py [--skip-ci] [--expect-green]
#
# The build runs from the Rust repo (as the Scala service runs from its own,
# so ASYNCAPI_HTML_DIR's default target/asyncapi-docs resolves there; render
# it first with services/user-service-rs/scripts/asyncapi-html.sh).
# Outcomes are informational unless --expect-green is given (used once the
# Rust items that satisfy the group are done). CONTRACT_* variables pass
# through to the harness (e.g. CONTRACT_READINESS_PATH=/health before RUST-2.4).
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
REPO="$PWD"
GROUP="${1:?usage: $0 checks/test_<group>.py [--skip-ci] [--expect-green]}"
shift
SKIP_CI=0
EXPECT_GREEN=0
for arg in "$@"; do
  case "$arg" in
    --skip-ci) SKIP_CI=1 ;;
    --expect-green) EXPECT_GREEN=1 ;;
  esac
done

. "$(dirname "$SELF")/lib/owner.sh"
run_as_owner "$PWD" "$SELF" "$GROUP" "$@"

passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
SCRATCH="$(mktemp -d /tmp/verify-check-group.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT
RUST_REPO="$(realpath ../../services/user-service-rs)"
BIN="$RUST_REPO/target/debug/user-service"

echo "== 1. CI (scripts/ci.sh) =="
if [ "$SKIP_CI" = 1 ]; then
  echo "skip --skip-ci given"
elif scripts/ci.sh > "$SCRATCH/ci.log" 2>&1; then
  ok "$(grep -Eo '[0-9]+ passed' "$SCRATCH/ci.log" | tail -1), $(grep -Eo 'Total coverage: [0-9.]+%' "$SCRATCH/ci.log")"
else
  bad "scripts/ci.sh failed"
  tail -8 "$SCRATCH/ci.log" | sed 's/^/     /'
fi

echo "== 2. Every check in $GROUP names its source =="
.venv/bin/python - "$GROUP" > "$SCRATCH/sources.txt" 2>&1 << 'PY'
import ast, re, sys
from gluon_contract.contracts import CONTRACTS_ROOT, latest_capture
capture = latest_capture(CONTRACTS_ROOT, "user-service")
tree = ast.parse(open(sys.argv[1]).read())
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
        doc = ast.get_docstring(node) or ""
        source = next((l.strip() for l in doc.splitlines() if l.strip().startswith("Source:")), "")
        missing = [f for f in re.findall(r"http/([a-z0-9-]+)\.txt", doc)
                   if "<" not in f and not (capture / "http" / f"{f}.txt").is_file()]
        print(f"{node.name}\t{source}\t{' '.join(missing)}")
PY
while IFS=$'\t' read -r name source missing; do
  if [ -z "$source" ]; then
    bad "$name: no Source: line"
  elif [ -n "$missing" ]; then
    bad "$name cites capture files that don't exist: $missing"
  else
    ok "$name — ${source#Source: }"
  fi
done < "$SCRATCH/sources.txt"

echo "== 3. The group against the Rust build =="
if (cd "$RUST_REPO" && cargo build -q --locked -p user-service) > "$SCRATCH/build.log" 2>&1; then
  ok "built $BIN"
else
  bad "cargo build failed"
  tail -5 "$SCRATCH/build.log" | sed 's/^/     /'
fi
uv run --no-sync pytest "$GROUP" -p no:cacheprovider -rA --tb=line -q \
  --target-cmd "$BIN" --target-cwd "$RUST_REPO" --target-name user-service-rs > "$SCRATCH/run.log" 2>&1
grep -E "^gluon-contract:" "$SCRATCH/run.log" | sed 's/^/     /'
green=0
red=0
while read -r outcome test rest; do
  name="${test##*::}"
  if [ "$outcome" = PASSED ]; then
    green=$((green + 1))
    echo "pass $name"
  else
    red=$((red + 1))
    echo "red  $name${rest:+ $rest}"
  fi
done < <(grep -E '^(PASSED|FAILED|ERROR) [^ ]+::' "$SCRATCH/run.log")
summary="$(tail -1 "$SCRATCH/run.log")"
if [ "$EXPECT_GREEN" = 1 ]; then
  [ "$red" = 0 ] && [ "$green" -gt 0 ] && ok "all $green checks green" || bad "$red of $((green + red)) checks red: $summary"
else
  ok "group ran against the Rust build: $green green, $red red (informational until its Rust items are done)"
fi

echo
total=$((passed + failed))
if [ "$failed" = 0 ]; then
  echo "PASS: $GROUP verified ($passed checks)"
else
  echo "FAIL: $failed of $total checks failed"
  exit 1
fi
