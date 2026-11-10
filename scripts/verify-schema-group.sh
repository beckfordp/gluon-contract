#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track schema-group_20261109 (gluon PLAN.md RUST-1.5): the schema and
# stored-format group.
#   scripts/verify-schema-group.sh [--skip-ci] [--expect-green]
exec "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/verify-check-group.sh" checks/test_schema.py "$@"
