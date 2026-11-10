#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track isolated-runner_20261108 (gluon PLAN.md RUST-1.2): the
# isolated-mode runner, end to end, from outside the harness where it can.
#   1. CI: format, lint, types, unit + integration tests, coverage
#   2. Config: an unusable configuration stops a run, listing every problem
#   3. A live run, held open around the stand-in target (a test double) and
#      probed with curl, psql and ps: readiness, the exact env-var contract,
#      Postgres over TCP with a password, logical WAL, the OTLP stub, the
#      target's span, log line and metrics
#   4. Teardown: no process, directory or listening port left
#   5. A target that fails to start (deliberately): reported with its own
#      output, nothing left
#   6. The checks/ entry point and its options, with a throwaway check
#   7. contracts/: every capture has its PROVENANCE.md
# Each result is printed as it is found; the exit status is 0 only if all pass.
#
#   scripts/verify-isolated-runner.sh [--skip-ci]
#
# Runs as the repo's owner. From the sandbox's root desktop terminal it
# re-runs itself as that user: PostgreSQL refuses to run as root, and files
# root created in the repo would be unusable to its owner.
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
REPO="$PWD"

owner="$(stat -c %U "$REPO")"
if [ "$(id -un)" != "$owner" ]; then
  if [ "$(id -u)" = 0 ] && command -v runuser > /dev/null; then
    home="$(getent passwd "$owner" | cut -d: -f6)"
    echo "== re-running as $owner (PostgreSQL won't run as root; repo files stay $owner's) =="
    exec runuser -u "$owner" -- env HOME="$home" PATH="$PATH" LANG=C.UTF-8 bash "$SELF" "$@"
  fi
  echo "FAIL run as $owner, who owns $REPO"
  exit 1
fi

SKIP_CI=0
[ "${1:-}" = "--skip-ci" ] && SKIP_CI=1

passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
# check DESCRIPTION COMMAND...: ok if the command succeeds (output hidden).
check() {
  local description="$1"
  shift
  if "$@" > /dev/null 2>&1; then ok "$description"; else bad "$description"; fi
}
# expect DESCRIPTION EXPECTED ACTUAL
expect() {
  if [ "$2" != "$3" ]; then
    bad "$1 (expected '$2', got '$3')"
  elif [ -n "$3" ]; then
    ok "$1: $3"
  else
    ok "$1"
  fi
}
port_open() { (exec 3<> "/dev/tcp/127.0.0.1/$1") 2> /dev/null; }
http_code() { curl -s -m 5 -o /dev/null -w '%{http_code}' "$@" || true; }
json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1"; }

SCRATCH="$(mktemp -d /tmp/verify-isolated-runner.XXXXXX)"
HOLDER_PID=""
cleanup() {
  [ -n "$HOLDER_PID" ] && kill -TERM "$HOLDER_PID" 2> /dev/null && wait "$HOLDER_PID" 2> /dev/null
  rm -rf "$SCRATCH"
}
trap cleanup EXIT

PYTHON="$REPO/.venv/bin/python"
STAND_IN="$REPO/tests/integration/stand_in_target.py"
STAND_IN_CMD="$PYTHON $STAND_IN"

echo "== Prerequisites =="
check "uv on the PATH ($(uv --version 2> /dev/null))" command -v uv
check "the project's virtualenv ($PYTHON)" test -x "$PYTHON"
PG_BIN="$("$PYTHON" -c 'import os; from gluon_contract.config import find_pg_bin; print(find_pg_bin(os.environ.get("CONTRACT_PG_BIN")))' 2> /dev/null)"
if [ -n "$PG_BIN" ]; then
  ok "PostgreSQL binaries: $PG_BIN ($("$PG_BIN/postgres" --version))"
else
  bad "PostgreSQL binaries not found (pg_ctl on the PATH, or CONTRACT_PG_BIN)"
fi

echo "== 1. CI (scripts/ci.sh) =="
if [ "$SKIP_CI" = 1 ]; then
  echo "skip --skip-ci given"
else
  echo "     (about 80 s: the integration tests start real Postgres clusters)"
  if scripts/ci.sh > "$SCRATCH/ci.log" 2>&1; then
    ok "format, lint, mypy (src, tests, checks): clean"
    ok "$(grep -Eo '[0-9]+ passed[^=]*' "$SCRATCH/ci.log" | tail -1 | sed 's/ *$//')"
    ok "$(grep -Eo 'Total coverage: [0-9.]+%' "$SCRATCH/ci.log")"
  else
    bad "scripts/ci.sh failed; its last lines:"
    tail -15 "$SCRATCH/ci.log" | sed 's/^/     /'
  fi
fi

echo "== 2. An unusable configuration stops the run =="
mkdir -p "$SCRATCH/suite"
cp checks/conftest.py "$SCRATCH/suite/conftest.py"
cat > "$SCRATCH/suite/test_probe.py" << 'EOF'
import os
import urllib.request
from pathlib import Path


def test_ready(harness):
    Path(os.environ["VERIFY_RECORD"]).write_text(str(harness.work_dir))
    with urllib.request.urlopen(harness.base_url + "/health/ready") as response:
        assert response.status == 200
EOF
out="$(env -u CONTRACT_TARGET_CMD CONTRACT_SERVICE=Users uv run --no-sync pytest -p no:cacheprovider "$SCRATCH/suite" 2>&1)"
code=$?
expect "exit status is a usage error" 4 "$code"
grep -q "CONTRACT_TARGET_CMD is required" <<< "$out" && grep -q "CONTRACT_SERVICE must look like" <<< "$out" \
  && ok "one message lists both problems" || bad "problems not both listed: $(tail -3 <<< "$out")"

echo "== 3. A live run, held open around the stand-in =="
cat > "$SCRATCH/hold.py" << 'EOF'
"""Holds one harness open until SIGTERM, describing it in a JSON file."""
import json, signal, sys, threading
from pathlib import Path
from gluon_contract.config import load_config
from gluon_contract.env_contract import service_env
from gluon_contract.harness import Harness

stand_in_cmd, info, root = sys.argv[1:4]
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
config = load_config({"CONTRACT_TARGET_CMD": stand_in_cmd, "CONTRACT_TARGET_NAME": "stand-in"}, cwd=Path(root))
base = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8", "VERIFY_LEAK": "must-not-reach-the-target"}
with Harness(config, base_env=base, work_root=Path(root)) as h:
    (span,) = h.otlp.wait_for_spans(lambda s: s.name == "stand-in.start")
    Path(info).write_text(json.dumps({
        "base_url": h.base_url, "metrics_url": h.metrics_url, "otlp": h.otlp.endpoint,
        "otlp_port": h.otlp.port, "http_port": h.endpoints.http_port,
        "metrics_port": h.endpoints.metrics_port, "pg_port": h.postgres.endpoint.port,
        "work_dir": str(h.work_dir), "data_dir": str(h.postgres.data_dir),
        "target_pid": h.target._process.pid if h.target._process else 0,
        "span_service": span.service_name,
        "expected_env": service_env(config.service, h.endpoints, base_env=base),
    }))
    stop.wait()
Path(info + ".stopped").write_text("ok")
EOF
mkdir -p "$SCRATCH/world"
INFO="$SCRATCH/world.json"
"$PYTHON" "$SCRATCH/hold.py" "$STAND_IN_CMD" "$INFO" "$SCRATCH/world" > "$SCRATCH/hold.log" 2>&1 &
HOLDER_PID=$!
for _ in $(seq 1 600); do
  [ -s "$INFO" ] && break
  kill -0 "$HOLDER_PID" 2> /dev/null || break
  sleep 0.1
done
if [ ! -s "$INFO" ]; then
  bad "the harness didn't come up; its output:"
  sed 's/^/     /' "$SCRATCH/hold.log"
else
  BASE_URL="$(json "$INFO" 'd["base_url"]')"
  WORK_DIR="$(json "$INFO" 'd["work_dir"]')"
  DATA_DIR="$(json "$INFO" 'd["data_dir"]')"
  PG_PORT="$(json "$INFO" 'd["pg_port"]')"
  OTLP="$(json "$INFO" 'd["otlp"]')"
  TARGET_PID="$(json "$INFO" 'd["target_pid"]')"
  PORTS="$(json "$INFO" '" ".join(str(d[k]) for k in ("http_port", "metrics_port", "otlp_port", "pg_port"))')"
  ok "harness up: work dir $WORK_DIR"

  expect "target ready: GET /health/ready" 200 "$(http_code "$BASE_URL/health/ready")"
  curl -s -m 5 "$BASE_URL/__env" > "$SCRATCH/env.json"
  python3 - "$SCRATCH/env.json" "$INFO" << 'EOF' && ok "target got exactly the env-var contract (no VERIFY_LEAK, no CONTRACT_*)" || bad "env-var contract differs (above)"
import json, sys
got, expected = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))["expected_env"]
if got != expected:
    for key in sorted(set(got) | set(expected)):
        if got.get(key) != expected.get(key):
            print(f"     {key}: expected {expected.get(key)!r}, got {got.get(key)!r}")
    sys.exit(1)
EOF
  python3 -c "import json,sys; e=json.load(open(sys.argv[1])); print('     ' + ', '.join(sorted(e)))" "$SCRATCH/env.json"

  login="host=127.0.0.1 port=$PG_PORT user=user dbname=user connect_timeout=5"
  expect "Postgres: the domain user logs in over TCP with its password" "user user" \
    "$("$PG_BIN/psql" -X -tA -c "select current_user || ' ' || current_database()" "$login password=user" 2> /dev/null)"
  "$PG_BIN/psql" -X -tA -c "select 1" "$login password=wrong" > /dev/null 2>&1 \
    && bad "Postgres accepted a wrong password" || ok "Postgres refuses a wrong password (scram-sha-256)"
  expect "Postgres: wal_level" logical "$("$PG_BIN/psql" -X -tA -c "show wal_level" "$login password=user" 2> /dev/null)"

  expect "OTLP stub: the target's startup span arrived, service.name" user-service "$(json "$INFO" 'd["span_service"]')"
  expect "OTLP stub: POST /v1/traces (OTLP/JSON) answers" 200 \
    "$(http_code -H 'Content-Type: application/json' --data '{"resourceSpans":[]}' "$OTLP/v1/traces")"
  expect "OTLP stub: an unknown media type answers" 415 \
    "$(http_code -H 'Content-Type: text/plain' --data 'x' "$OTLP/v1/traces")"
  expect "OTLP stub: any other path answers" 404 "$(http_code "$OTLP/v1/metrics")"

  grep -q "stand_in_up 1" <<< "$(curl -s -m 5 "$(json "$INFO" 'd["metrics_url"]')")" \
    && ok "metrics endpoint scraped: stand_in_up 1" || bad "metrics endpoint didn't answer"
  grep -q '^{"@timestamp"' "$WORK_DIR/target.log" \
    && ok "target's stdout captured: JSON log line in target.log" || bad "no JSON log line in $WORK_DIR/target.log"

  echo "== 4. Teardown =="
  kill -TERM "$HOLDER_PID"
  wait "$HOLDER_PID" 2> /dev/null
  HOLDER_PID=""
  check "the harness stopped cleanly" test -f "$INFO.stopped"
  check "work directory removed" test ! -e "$WORK_DIR"
  [ -z "$(pgrep -f -- "-D $DATA_DIR" || true)" ] && ok "no Postgres left for that data directory" || bad "Postgres still running"
  kill -0 "$TARGET_PID" 2> /dev/null && bad "target process $TARGET_PID still alive" || ok "target process $TARGET_PID gone"
  open_ports=""
  for port in $PORTS; do port_open "$port" && open_ports="$open_ports $port"; done
  expect "no port left listening (target, metrics, OTLP, Postgres: $PORTS)" "" "$open_ports"
fi

echo "== 5. A target that fails to start is handled (the failure is deliberate) =="
mkdir -p "$SCRATCH/failed"
out="$("$PYTHON" - "$STAND_IN_CMD --exit 3" "$SCRATCH/failed" << 'EOF' 2>&1
import sys
from pathlib import Path
from gluon_contract.config import load_config
from gluon_contract.harness import Harness
from gluon_contract.target import TargetError
config = load_config({"CONTRACT_TARGET_CMD": sys.argv[1]}, cwd=Path(sys.argv[2]))
try:
    Harness(config, work_root=Path(sys.argv[2])).__enter__()
except TargetError as error:
    print(error)
EOF
)"
if grep -q "exited with code 3 before it was ready" <<< "$out" && grep -q "stand-in: exiting as asked" <<< "$out"; then
  ok "reported with the exit code and the target's own output"
else
  bad "not the expected TargetError; got (last lines):"
  tail -8 <<< "$out" | sed 's/^/     /'
fi
expect "nothing left in its work root" "" "$(ls -A "$SCRATCH/failed")"
left="$(pgrep -af -- "$SCRATCH/failed" || true)"
[ -z "$left" ] && ok "no process left" || bad "processes left: $(tr '\n' ';' <<< "$left")"

echo "== 6. The checks/ entry point =="
# Collect only: the groups exist now (RUST-1.3 on), and running them against
# the stand-in would just fail them.
out="$(uv run --no-sync pytest -p no:cacheprovider checks --collect-only --target-cmd "$STAND_IN_CMD" --target-name stand-in 2>&1)"
code=$?
grep -q "gluon-contract: target stand-in ($STAND_IN_CMD) as user-service" <<< "$out" \
  && ok "pytest checks: options recognised, target named in the header" || bad "no header: $(head -5 <<< "$out")"
expect "pytest checks: the check groups collect (exit 0)" 0 "$code"

export VERIFY_RECORD="$SCRATCH/recorded-work-dir"
out="$(uv run --no-sync pytest -p no:cacheprovider "$SCRATCH/suite" --target-cmd "$STAND_IN_CMD" 2>&1)"
code=$?
expect "a throwaway check gets a ready harness and passes" 0 "$code"
[ "$code" = 0 ] || tail -5 <<< "$out" | sed 's/^/     /'
recorded="$(cat "$VERIFY_RECORD" 2> /dev/null)"
[ -n "$recorded" ] && [ ! -e "$recorded" ] && ok "its work directory is gone afterwards" || bad "work directory left: $recorded"

out="$(uv run --no-sync pytest -p no:cacheprovider "$SCRATCH/suite" --target-cmd "$STAND_IN_CMD" --keep-artifacts 2>&1)"
recorded="$(cat "$VERIFY_RECORD" 2> /dev/null)"
[ -f "$recorded/target.log" ] && [ -f "$recorded/postgres.log" ] \
  && ok "--keep-artifacts keeps target.log and postgres.log" || bad "--keep-artifacts kept nothing at $recorded"
rm -rf "$recorded"

echo "== 7. contracts/ =="
out="$("$PYTHON" -c '
from gluon_contract.contracts import CONTRACTS_ROOT, capture_dirs
for service in sorted(p for p in CONTRACTS_ROOT.iterdir() if p.is_dir()):
    captures = capture_dirs(CONTRACTS_ROOT, service.name)
    print(f"{service.name}: {len(captures)} capture(s)")
' 2>&1)" && ok "every capture has its PROVENANCE.md ($(tr '\n' ';' <<< "$out" | sed 's/;$//'))" || bad "$out"
check "capture instructions present (contracts/user-service/CAPTURE.md)" test -f contracts/user-service/CAPTURE.md

echo
total=$((passed + failed))
if [ "$failed" = 0 ]; then
  echo "PASS: RUST-1.2 isolated-mode runner verified ($passed checks)"
else
  echo "FAIL: $failed of $total checks failed"
  exit 1
fi
