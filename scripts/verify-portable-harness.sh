#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track portable-harness_20261110: the harness's tests and verify
# scripts run the same on macOS and Linux (Ubuntu).
#   1. The shared owner helper (scripts/lib/owner.sh): its tests pass, every
#      verify script's opening runs on this OS, and none calls a GNU-only or
#      Linux-only command for it directly
#   2. The test doubles and process checks without /proc: the integration
#      tests pass, and so does verify-isolated-runner.sh (--skip-ci)
#   3. Everything else: scripts/ci.sh, then every other verify-*.sh. Needs
#      cargo on the PATH, the CDC jars (gluon bin/sandbox-setup --only cdc),
#      the Rust service's AsyncAPI HTML (its scripts/asyncapi-html.sh) and,
#      for verify-cluster-mode.sh, PostgreSQL 16 binaries (CONTRACT_PG_BIN)
# Each result is printed as it is found; the exit status is 0 only if all pass.
#
#   scripts/verify-portable-harness.sh
#
# Runs as the repo's owner. From the sandbox's root desktop terminal it
# re-runs itself as that user.
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."

. scripts/lib/owner.sh
run_as_owner "$PWD" "$SELF" "$@"

passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }

# The scripts that start with the "run as the repo's owner" opening.
OPENINGS=(verify-check-group verify-cluster-mode verify-implicit-behaviours
  verify-isolated-runner verify-probe-group verify-probe-stubs verify-cdc-group)

echo "== 1. The shared owner helper on $(uname -s) =="
if out="$(uv run pytest -q -p no:cacheprovider --no-cov tests/unit/test_owner_sh.py 2>&1)"; then
  ok "its tests pass: $(tail -1 <<< "$out")"
else
  bad "its tests fail:"
  sed 's/^/     /' <<< "$out" | tail -20
fi

# Each script's opening, up to the owner check (and cdc-group's home lookup),
# run on its own: it must reach the end without a usage error from stat,
# getent or any other tool.
for name in "${OPENINGS[@]}"; do
  script="scripts/$name.sh"
  opening="$(awk '{ print } /^run_as_owner |^home=/ { exit }' "$script" |
    sed "s|\"\${BASH_SOURCE\[0\]}\"|\"$PWD/$script\"|")"
  # verify-check-group's opening needs a group to check; the others ignore it.
  if out="$(bash -c "$opening"$'\n''echo opening-done' "$name" checks/test_rest.py 2>&1)" &&
    [ "$(tail -1 <<< "$out")" = opening-done ]; then
    ok "$name: the opening runs"
  else
    bad "$name: the opening stops:"
    sed 's/^/     /' <<< "$out"
  fi
done

if hits="$(grep -n -E 'stat -c|getent|/proc/' scripts/verify-*.sh | grep -v '^scripts/verify-portable-harness.sh:')"; then
  bad "verify scripts still call a GNU/Linux-only command directly:"
  sed 's/^/     /' <<< "$hits"
else
  ok "no verify script calls stat -c, getent or /proc directly"
fi

echo "== 2. Test doubles and process checks without /proc =="
if out="$(uv run pytest -q -p no:cacheprovider --no-cov tests/integration 2>&1)"; then
  ok "the integration tests pass: $(tail -1 <<< "$out")"
else
  bad "the integration tests fail:"
  grep -E '^(FAILED|ERROR)|passed|failed' <<< "$out" | sed 's/^/     /' | tail -20
fi
if out="$(scripts/verify-isolated-runner.sh --skip-ci 2>&1)"; then
  ok "verify-isolated-runner.sh --skip-ci: $(tail -1 <<< "$out")"
else
  bad "verify-isolated-runner.sh --skip-ci:"
  grep -E '^FAIL' <<< "$out" | sed 's/^/     /'
fi

echo "== 3. ci.sh and every verify script =="
RUST="../../services/user-service-rs"
missing=()
command -v cargo > /dev/null || missing+=("cargo on the PATH")
[ -f "${CONTRACT_CDC_HOME:-$(owner_home "$(repo_owner .)")/.local/cdc-kafka-3.8.0_debezium-3.0.0.Final}/COMPLETE" ] ||
  missing+=("the CDC jars (gluon bin/sandbox-setup --only cdc)")
[ -f "$RUST/target/asyncapi-docs/index.html" ] ||
  missing+=("the Rust AsyncAPI HTML ($RUST/scripts/asyncapi-html.sh)")
if [ "${#missing[@]}" != 0 ]; then
  for m in "${missing[@]}"; do bad "prerequisite missing: $m"; done
else
  ok "prerequisites: cargo, the CDC jars, the Rust AsyncAPI HTML"
  if out="$(scripts/ci.sh 2>&1)"; then
    ok "scripts/ci.sh: $(grep -E 'passed' <<< "$out" | tail -1 | tr -d '=' | sed 's/^ *//')"
  else
    bad "scripts/ci.sh fails:"
    grep -E '^(FAILED|ERROR)|passed|failed|Required' <<< "$out" | sed 's/^/     /' | tail -20
  fi
  # verify-check-group.sh is run by the per-group wrappers; this script and
  # verify-isolated-runner.sh are covered above.
  for script in scripts/verify-*.sh; do
    case "$script" in
      */verify-check-group.sh | */verify-portable-harness.sh | */verify-isolated-runner.sh) continue ;;
      */verify-implicit-behaviours.sh | */verify-cluster-mode.sh) args=() ;;
      *) args=(--skip-ci) ;;
    esac
    name="$(basename "$script" .sh)"
    if out="$("$script" ${args[@]+"${args[@]}"} 2>&1)"; then
      ok "$name: $(grep -E '^PASS' <<< "$out" | tail -1)"
    else
      bad "$name:"
      grep -E '^FAIL' <<< "$out" | sed 's/^/     /' | tail -10
    fi
  done
fi

echo
total=$((passed + failed))
if [ "$failed" = 0 ]; then
  echo "PASS: portable harness verified ($passed checks)"
else
  echo "FAIL: $failed of $total checks failed"
  exit 1
fi
