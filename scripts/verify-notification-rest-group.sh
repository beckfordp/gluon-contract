#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track ns-rest_20261113 (gluon RPN-4): notification-service's REST
# check group, seeded with its capture's rows, seen failing against the walking
# skeleton. Extended each phase; each result is printed as it is found.
#   1. CI (scripts/ci.sh)
#   2. The seed, seen from outside: the capture's rows inserted
#      (gluon_contract.sent_email) into a throwaway Postgres holding the
#      capture's own schema (db/schema.sql, loaded with psql), then dumped
#      as CAPTURE.sh dumped them (psql, row_to_json, order by created_at, UTC):
#      byte for byte db/sent-email.jsonl
#   3. The seed reproduces every captured /emails answer, each reported
#   4. The REST group against the walking skeleton, through
#      scripts/verify-check-group.sh --service notification-service: every
#      check names its source, and every check is red with "got 404" (the
#      skeleton has no /emails route; its health checks are RPN-2's)
#   5. Checks selected by service: a notification-service run collects only
#      checks/test_notification_rest.py; a user-service run collects none of it
# The exit status is 0 only if all pass.
#
#   scripts/verify-notification-rest-group.sh [--skip-ci]
#
# Runs as the repo's owner. From the sandbox's root desktop terminal it
# re-runs itself as that user.
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."

. "$(dirname "$SELF")/lib/owner.sh"
run_as_owner "$PWD" "$SELF" "$@"

SKIP_CI=0
for arg in "$@"; do
  case "$arg" in
    --skip-ci) SKIP_CI=1 ;;
  esac
done

passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
SCRATCH="$(mktemp -d /tmp/verify-notification-rest-group.XXXXXX)"
cleanup() {
  [ -f "$SCRATCH/pg/postmaster.pid" ] && "$PG_BIN/pg_ctl" stop -D "$SCRATCH/pg" -m fast > /dev/null 2>&1
  rm -rf "$SCRATCH"
}
trap cleanup EXIT
PYTHON="$PWD/.venv/bin/python"
# The PostgreSQL binaries as a run finds them (CONTRACT_PG_BIN, else pg_ctl's real directory)
PG_BIN="$("$PYTHON" -c 'import os
from gluon_contract.config import find_pg_bin
print(find_pg_bin(os.environ.get("CONTRACT_PG_BIN")))')"
CAPTURE="$("$PYTHON" -c 'from gluon_contract.contracts import CONTRACTS_ROOT, latest_capture
print(latest_capture(CONTRACTS_ROOT, "notification-service"))')"

echo "== 1. CI (scripts/ci.sh) =="
if [ "$SKIP_CI" = 1 ]; then
  echo "skip --skip-ci given"
elif scripts/ci.sh > "$SCRATCH/ci.log" 2>&1; then
  ok "$(grep -Eo '[0-9]+ passed' "$SCRATCH/ci.log" | tail -1), $(grep -Eo 'Total coverage: [0-9.]+%' "$SCRATCH/ci.log")"
else
  bad "scripts/ci.sh failed"
  tail -8 "$SCRATCH/ci.log" | sed 's/^/     /'
fi

echo "== 2. The seed, seen from outside (capture $(basename "$CAPTURE")) =="
psql_ns() { "$PG_BIN/psql" --no-psqlrc -h "$SCRATCH" -U notification -d notification "$@"; }
if "$PG_BIN/initdb" -D "$SCRATCH/pg" -U notification --auth=trust > "$SCRATCH/initdb.log" 2>&1 \
  && "$PG_BIN/pg_ctl" start -D "$SCRATCH/pg" -l "$SCRATCH/pg.log" -w \
    -o "-c listen_addresses='' -c unix_socket_directories=$SCRATCH -c timezone=UTC" > /dev/null 2>&1 \
  && "$PG_BIN/createdb" -h "$SCRATCH" -U notification notification; then
  ok "throwaway Postgres $("$PG_BIN/postgres" --version | grep -Eo '[0-9]+\.[0-9]+' | head -1)"
else
  bad "throwaway Postgres didn't start"
  tail -5 "$SCRATCH/pg.log" "$SCRATCH/initdb.log" 2> /dev/null | sed 's/^/     /'
fi
if psql_ns -q -v ON_ERROR_STOP=1 -f "$CAPTURE/db/schema.sql" > "$SCRATCH/schema.log" 2>&1; then
  ok "the capture's schema loaded: $(psql_ns -tAc "select count(*) from information_schema.columns where table_name = 'sent_email'") sent_email columns"
else
  bad "db/schema.sql didn't load"
  tail -5 "$SCRATCH/schema.log" | sed 's/^/     /'
fi
if "$PYTHON" - "$SCRATCH" > "$SCRATCH/seed.log" 2>&1 << 'PY'
import sys

import psycopg

from gluon_contract.sent_email import captured_rows, insert

with psycopg.connect(host=sys.argv[1], dbname="notification", user="notification") as connection:
    insert(connection, captured_rows())
PY
then
  ok "seeded: $(psql_ns -tAc "select count(*) from sent_email") rows"
else
  bad "seeding failed"
  tail -5 "$SCRATCH/seed.log" | sed 's/^/     /'
fi
psql_ns -tAc "select row_to_json(s) from sent_email s order by created_at" > "$SCRATCH/dumped.jsonl" 2>&1
if cmp -s "$SCRATCH/dumped.jsonl" "$CAPTURE/db/sent-email.jsonl"; then
  ok "dumped as CAPTURE.sh did: byte for byte db/sent-email.jsonl ($(wc -l < "$SCRATCH/dumped.jsonl") lines)"
else
  bad "the dump differs from db/sent-email.jsonl"
  diff "$CAPTURE/db/sent-email.jsonl" "$SCRATCH/dumped.jsonl" | head -6 | cut -c1-160 | sed 's/^/     /'
fi

echo "== 3. The seed reproduces every captured /emails answer =="
uv run --no-sync pytest tests/unit/test_sent_email.py -k reproduces -p no:cacheprovider --no-cov \
  -rA --tb=line -q > "$SCRATCH/reproduces.log" 2>&1
while read -r outcome test rest; do
  answer="${test##*\[}"
  if [ "$outcome" = PASSED ]; then
    ok "http/${answer%\]}.txt"
  else
    bad "http/${answer%\]}.txt${rest:+ $rest}"
  fi
done < <(grep -E '^(PASSED|FAILED|ERROR) [^ ]+::' "$SCRATCH/reproduces.log")
grep -qE '^(PASSED|FAILED|ERROR) ' "$SCRATCH/reproduces.log" || bad "no answer checked: $(tail -1 "$SCRATCH/reproduces.log")"

echo "== 4. The REST group against the walking skeleton =="
if scripts/verify-check-group.sh checks/test_notification_rest.py --service notification-service --skip-ci \
  --expect-red "got 404" > "$SCRATCH/group.log" 2>&1; then
  ok "checks/test_notification_rest.py: $(grep -c '^ok   test_' "$SCRATCH/group.log") checks name their source;" \
    "$(grep -Eo 'all [0-9]+ checks red.*' "$SCRATCH/group.log")"
else
  bad "checks/test_notification_rest.py (scripts/verify-check-group.sh):"
  grep -E '^(FAIL|     )' "$SCRATCH/group.log" | head -12 | cut -c1-160 | sed 's/^/     /'
fi

echo "== 5. Checks selected by service =="
collect() {
  uv run --no-sync pytest checks --collect-only -q -p no:cacheprovider --service "$1" 2> /dev/null | grep '::'
}
modules() { cut -d: -f1 | sort -u | tr '\n' ' '; }
ns="$(collect notification-service)"
us="$(collect user-service)"
ns_modules="$(modules <<< "$ns")"
if [ "$ns_modules" = "checks/test_notification_rest.py " ]; then
  ok "a notification-service run collects only checks/test_notification_rest.py: $(grep -c . <<< "$ns") checks"
else
  bad "a notification-service run collects: ${ns_modules:-nothing}"
fi
if [ -n "$us" ] && ! grep -q '^checks/test_notification_rest.py::' <<< "$us"; then
  ok "a user-service run collects none of it: $(grep -c . <<< "$us") checks from $(modules <<< "$us" | wc -w) modules"
else
  bad "a user-service run collects test_notification_rest.py, or nothing"
fi

echo
total=$((passed + failed))
if [ "$failed" = 0 ]; then
  echo "PASS: ns-rest_20261113 verified ($passed checks)"
else
  echo "FAIL: $failed of $total checks failed"
  exit 1
fi
