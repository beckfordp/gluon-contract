#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track docs-group_20261109 (gluon PLAN.md RUST-1.4): the docs group.
# Red against the Rust build until RUST-4.1/4.2 (informational); pass
# --expect-green once they are done.
#   scripts/verify-docs-group.sh [--skip-ci] [--expect-green]
exec "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/verify-check-group.sh" checks/test_user_docs.py "$@"
