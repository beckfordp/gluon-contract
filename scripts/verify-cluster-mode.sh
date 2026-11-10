#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track cluster-mode_20261110 (gluon PLAN.md RUST-5.4, prepared): which
# checks cluster mode runs, and cluster mode end to end against a started Rust
# service standing in for a deployment (tests/integration/test_cluster_mode.py).
# On the laptop, against gluon-local (see gluon docs/rust-spike-verification.md):
#   uv run pytest checks --base-url http://user-service.gluon-local.svc.cluster.local:8080
#   scripts/verify-cluster-mode.sh
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
owner="$(stat -c %U .)"
if [ "$(id -un)" != "$owner" ]; then
  if [ "$(id -u)" = 0 ] && command -v runuser > /dev/null; then
    echo "== re-running as $owner (the repo's owner) =="
    exec runuser -u "$owner" -- env HOME="$(getent passwd "$owner" | cut -d: -f6)" PATH="$PATH" \
      LANG=C.UTF-8 bash "$SELF" "$@"
  fi
  echo "FAIL run as $owner"
  exit 1
fi
passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
RUST_REPO="$(realpath ../../services/user-service-rs)"

echo "== 1. What cluster mode runs =="
collected="$(CONTRACT_BASE_URL=http://unused.invalid uv run --no-sync pytest checks --collect-only -q -m 'cluster and not isolated' 2> /dev/null | grep -c '::')"
all="$(uv run --no-sync pytest checks --collect-only -q --target-cmd x 2> /dev/null | grep -c '::')"
if [ "$collected" -gt 0 ]; then ok "$collected of $all checks run in cluster mode (REST, docs, the topic check)"; else bad "no check is marked cluster"; fi

echo "== 2. Cluster mode against a started service and the CDC stack =="
(cd "$RUST_REPO" && cargo build -q --locked -p user-service) || bad "cargo build failed"
log="$(mktemp)"
if uv run --no-sync pytest -q -rA tests/integration/test_cluster_mode.py > "$log" 2>&1; then
  ok "$(grep -E 'passed|skipped' "$log" | tail -1)"
else
  bad "tests/integration/test_cluster_mode.py failed:"
  tail -15 "$log" | sed 's/^/     /'
fi
grep -q "SKIPPED.*test_cluster_mode" "$log" && bad "the test was skipped (CDC jars or the build missing)"
rm -f "$log"

echo
if [ "$failed" = 0 ]; then
  echo "PASS: cluster mode verified ($passed checks)"
else
  echo "FAIL: $failed of $((passed + failed)) checks failed"
  exit 1
fi
