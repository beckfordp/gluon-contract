#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track scala-confirmation_20261110 (gluon PLAN.md RUST-5.0): the
# harness against the Scala service in isolated mode, every check green but
# the probe group's (Rust-only). The laptop pass's step B2 (gluon
# docs/ports/user-service-verification.md), each check's outcome reported as found.
#
#   scripts/verify-user-scala-confirmation.sh [--skip-ci] [--skip-stage]
#
# USER_SERVICE_DIR is the Scala service's checkout (default
# ../../services/user-service); its staged build runs from there, as it serves
# its AsyncAPI HTML from its own target/. The CDC group needs the jars from
# gluon bin/sandbox-setup --only cdc (or CONTRACT_CDC_HOME); CONTRACT_*
# variables pass through to the harness.
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
SKIP_CI=0
SKIP_STAGE=0
for arg in "$@"; do
  case "$arg" in
    --skip-ci) SKIP_CI=1 ;;
    --skip-stage) SKIP_STAGE=1 ;;
  esac
done

. "$(dirname "$SELF")/lib/owner.sh"
run_as_owner "$PWD" "$SELF" "$@"

passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
SCRATCH="$(mktemp -d /tmp/verify-user-scala-confirmation.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT
SCALA_REPO="$(realpath "${USER_SERVICE_DIR:-../../services/user-service}")"
BIN="$SCALA_REPO/target/universal/stage/bin/user-service"

echo "== 1. CI (scripts/ci.sh) =="
if [ "$SKIP_CI" = 1 ]; then
  echo "skip --skip-ci given"
elif scripts/ci.sh > "$SCRATCH/ci.log" 2>&1; then
  ok "$(grep -Eo '[0-9]+ passed' "$SCRATCH/ci.log" | tail -1), $(grep -Eo 'Total coverage: [0-9.]+%' "$SCRATCH/ci.log")"
else
  bad "scripts/ci.sh failed"
  tail -8 "$SCRATCH/ci.log" | sed 's/^/     /'
fi

echo "== 2. The staged Scala service =="
if [ "$SKIP_STAGE" = 1 ]; then
  echo "skip --skip-stage given"
else
  if [ -z "${GITHUB_TOKEN:-}" ]; then GITHUB_TOKEN="$(gh auth token 2> /dev/null)"; fi
  export GITHUB_TOKEN
  if (cd "$SCALA_REPO" && sbt -batch stage < /dev/null) > "$SCRATCH/stage.log" 2>&1; then
    ok "sbt stage in $SCALA_REPO"
  else
    bad "sbt stage failed"
    tail -8 "$SCRATCH/stage.log" | sed 's/^/     /'
  fi
fi
if [ -x "$BIN" ]; then ok "staged build $BIN"; else bad "no staged build at $BIN"; fi

echo "== 3. The harness against the Scala service =="
uv run --no-sync pytest checks --ignore checks/test_probe.py -p no:cacheprovider -rA --tb=line -q \
  --target-cmd "$BIN" --target-cwd "$SCALA_REPO" --target-name user-service-scala > "$SCRATCH/run.log" 2>&1
grep -E "^gluon-contract:" "$SCRATCH/run.log" | sed 's/^/     /'
green=0
grep -E '^(PASSED|FAILED|ERROR|SKIPPED)' "$SCRATCH/run.log" > "$SCRATCH/outcomes.txt"
while read -r outcome test rest; do
  name="${test##*::}"
  case "$outcome" in
    PASSED)
      green=$((green + 1))
      echo "pass $name"
      ;;
    SKIPPED) echo "skip $test${rest:+ $rest}" ;;
    *) echo "red  $name${rest:+ $rest}" ;;
  esac
done < "$SCRATCH/outcomes.txt"
for group in $(grep -Eo 'checks/test_[a-z_]+\.py' "$SCRATCH/outcomes.txt" | sort -u); do
  total="$(grep -c " $group" "$SCRATCH/outcomes.txt")"
  red="$(grep -Ev '^PASSED' "$SCRATCH/outcomes.txt" | grep -c " $group")"
  if [ "$red" = 0 ]; then
    ok "$group: $total green"
  else
    bad "$group: $red of $total red or skipped"
  fi
done
[ "$green" -gt 0 ] || bad "no check passed: $(tail -1 "$SCRATCH/run.log")"

echo "== 4. The two expectations RUST-5.0 corrected =="
for name in test_the_service_name_scopes_the_metrics test_the_openapi_spec_is_the_scala_one; do
  if grep -Eq "^PASSED [^ ]+::$name\$" "$SCRATCH/outcomes.txt"; then ok "$name"; else bad "$name not green"; fi
done

echo
total=$((passed + failed))
if [ "$failed" = 0 ]; then
  echo "PASS: RUST-5.0 confirmed — $green checks green against the Scala service ($passed checks)"
else
  echo "FAIL: $failed of $total checks failed"
  exit 1
fi
