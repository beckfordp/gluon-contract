#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track rest-group_20261109 (gluon PLAN.md RUST-1.3): the REST group.
# Before RUST-2.4 the Rust build has no /health/ready; set
# CONTRACT_READINESS_PATH=/health to see the group's red checks then.
#   scripts/verify-rest-group.sh [--skip-ci] [--expect-green]
exec "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/verify-check-group.sh" checks/test_user_rest.py "$@"
