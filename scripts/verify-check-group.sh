#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Runs one check group against the Rust build, each check's outcome reported as
# it is found: the tool for writing a group red, then seeing it green. That each
# check names its source and the capture files it cites exist is CI's
# (tests/unit/test_check_sources.py); the whole harness against the build is
# gluon bin/verify-port's contract step.
#
#   scripts/verify-check-group.sh checks/test_<group>.py [--service NAME]
#                                 [--expect-green | --expect-red PATTERN]
#
# --service (default user-service; gluon RPN-4) names the service the group
# judges: its Rust port services/<NAME>-rs and binary target/debug/<NAME>, and
# the harness run's --service.
# The build runs from the Rust repo (as the Scala service runs from its own,
# so ASYNCAPI_HTML_DIR's default target/asyncapi-docs resolves there; render
# it first with services/user-service-rs/scripts/asyncapi-html.sh).
# Outcomes are informational unless --expect-green is given (used once the
# Rust items that satisfy the group are done) or --expect-red PATTERN (a group
# written before them: every check fails, not errors, each failure holding
# PATTERN, its stated reason). CONTRACT_* variables pass through to the
# harness (e.g. CONTRACT_READINESS_PATH=/health before RUST-2.4).
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
USAGE="$0 checks/test_<group>.py [--service NAME] [--expect-green | --expect-red PATTERN]"
GROUP="${1:?usage: $USAGE}"
shift
ARGS=("$@")
SERVICE=user-service
EXPECT_GREEN=0
EXPECT_RED=""
while [ $# -gt 0 ]; do
  case "$1" in
    --service)
      SERVICE="${2:?usage: $USAGE}"
      shift
      ;;
    --expect-green) EXPECT_GREEN=1 ;;
    --expect-red)
      EXPECT_RED="${2:?usage: $USAGE}"
      shift
      ;;
  esac
  shift
done

. "$(dirname "$SELF")/lib/owner.sh"
run_as_owner "$PWD" "$SELF" "$GROUP" ${ARGS[@]+"${ARGS[@]}"}

passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
SCRATCH="$(mktemp -d /tmp/verify-check-group.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT
RUST_REPO="$(realpath "../../services/$SERVICE-rs")"
BIN="$RUST_REPO/target/debug/$SERVICE"

echo "== The group against the Rust build =="
if (cd "$RUST_REPO" && cargo build -q --locked -p "$SERVICE") > "$SCRATCH/build.log" 2>&1; then
  ok "built $BIN"
else
  bad "cargo build failed"
  tail -5 "$SCRATCH/build.log" | sed 's/^/     /'
fi
uv run --no-sync pytest "$GROUP" -p no:cacheprovider -rA --tb=line -q \
  --service "$SERVICE" --junitxml "$SCRATCH/run.xml" -o junit_logging=no \
  --target-cmd "$BIN" --target-cwd "$RUST_REPO" --target-name "$SERVICE-rs" > "$SCRATCH/run.log" 2>&1
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
elif [ -n "$EXPECT_RED" ]; then
  # Every check failed (no pass, error or skip), each failure holding the stated reason
  if .venv/bin/python - "$SCRATCH/run.xml" "$EXPECT_RED" > "$SCRATCH/red.txt" 2>&1 << 'PY'
import sys
import xml.etree.ElementTree as ET

report, reason = sys.argv[1], sys.argv[2]
try:
    cases = list(ET.parse(report).getroot().iter("testcase"))
except (OSError, ET.ParseError) as error:
    sys.exit(f"no junit report: {error}")
problems = []
for case in cases:
    name = case.get("name", "")
    failure = case.find("failure")
    if case.find("error") is not None:
        problems.append(f"{name}: error")
    elif case.find("skipped") is not None:
        problems.append(f"{name}: skipped")
    elif failure is None:
        problems.append(f"{name}: passes")
    elif reason not in (failure.get("message", "") + (failure.text or "")):
        problems.append(f"{name}: fails without {reason!r}: {failure.get('message', '')[:150]!r}")
print("\n".join(problems) or f"{len(cases)} red")
sys.exit(1 if problems or not cases else 0)
PY
  then
    ok "all $red checks red, each with '$EXPECT_RED'"
  else
    bad "not every check red with '$EXPECT_RED':"
    sed 's/^/     /' "$SCRATCH/red.txt"
  fi
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
