#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track portable-harness_20261110: the harness's tests and verify
# scripts run the same on macOS and Linux (Ubuntu).
#   1. The shared owner helper (scripts/lib/owner.sh): its tests pass, every
#      verify script's opening runs on this OS, and none calls a GNU-only or
#      Linux-only command for it directly
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

echo
total=$((passed + failed))
if [ "$failed" = 0 ]; then
  echo "PASS: portable harness verified ($passed checks)"
else
  echo "FAIL: $failed of $total checks failed"
  exit 1
fi
