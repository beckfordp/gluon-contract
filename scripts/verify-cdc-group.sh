#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track cdc-stack_20261109 (gluon PLAN.md RUST-1.8): the sandbox CDC
# stack (Kafka, Kafka Connect, Debezium from Maven Central jars) and the CDC
# group run against the Rust build: the real user-events record, and the
# outbox group's routing stand-in matching it.
#   scripts/verify-cdc-group.sh [--skip-ci]
# Needs the jars: gluon bin/sandbox-setup --only cdc (or CONTRACT_CDC_HOME).
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
home="${CONTRACT_CDC_HOME:-$(getent passwd "$(stat -c %U .)" | cut -d: -f6)/.local/cdc-kafka-3.8.0_debezium-3.0.0.Final}"
if [ -f "$home/COMPLETE" ]; then
  echo "ok   CDC jars in $home: $(cat "$home/COMPLETE")"
else
  echo "FAIL no CDC jars in $home: run gluon bin/sandbox-setup --only cdc"
  exit 1
fi
exec "$(dirname "$SELF")/verify-check-group.sh" checks/test_cdc.py "$@" --expect-green
