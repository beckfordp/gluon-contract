#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track telemetry-groups_20261109 (gluon PLAN.md RUST-1.7): the traces,
# metrics, logs and config groups, one after another (CI runs once, first).
# Red against the Rust build until RUST-3.2..3.4 (informational); pass
# --expect-green once they are done.
#   scripts/verify-telemetry-groups.sh [--skip-ci] [--expect-green]
set -uo pipefail
HERE="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
skip=()
expect=()
for arg in "$@"; do
  case "$arg" in
    --skip-ci) skip=(--skip-ci) ;;
    --expect-green) expect=(--expect-green) ;;
  esac
done
failed=()
for group in traces metrics logs config; do
  echo "######## checks/test_user_$group.py ########"
  # ${a[@]+"${a[@]}"}: bash 3.2 (macOS) calls an empty array unbound under set -u.
  "$HERE/verify-check-group.sh" "checks/test_user_$group.py" ${skip[@]+"${skip[@]}"} \
    ${expect[@]+"${expect[@]}"} || failed+=("$group")
  skip=(--skip-ci)
  echo
done
if [ "${#failed[@]}" = 0 ]; then
  echo "PASS: traces, metrics, logs and config groups verified"
else
  echo "FAIL: ${failed[*]}"
  exit 1
fi
