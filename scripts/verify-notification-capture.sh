#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track ns-capture_20261111 (gluon PLAN.md RPN-1): a notification-service
# capture checked on its own by gluon_contract.notification_capture. Each file is reported ok or
# FAIL, named relative to the capture; the last line is PASS, or FAIL with exit 1.
# Default: the latest capture in contracts/notification-service/.
#   scripts/verify-notification-capture.sh [capture dir]
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
# A relative capture dir means relative to where the script was started, not the repo
if [ $# -gt 0 ]; then
  case "$1" in
    /*) ;;
    *) set -- "$PWD/$1" "${@:2}" ;;
  esac
fi
cd "$(dirname "$SELF")/.."
. "$(dirname "$SELF")/lib/owner.sh"
run_as_owner "$PWD" "$SELF" "$@"
exec uv run --no-sync python -m gluon_contract.notification_capture check "$@"
