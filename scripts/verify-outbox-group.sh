#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track outbox-group_20261109 (gluon PLAN.md RUST-1.6): the outbox and
# envelope group. Red against the Rust build until RUST-3.1 (informational);
# pass --expect-green once it is done.
#   scripts/verify-outbox-group.sh [--skip-ci] [--expect-green]
exec "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/verify-check-group.sh" checks/test_outbox.py "$@"
