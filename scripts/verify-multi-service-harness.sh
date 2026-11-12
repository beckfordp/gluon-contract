#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Verifies track multi-service-harness_20261112 (gluon PLAN.md RPN-3): the
# harness takes the service as a parameter, and user-service runs unchanged.
#   1. CI: format, lint, types, unit + integration tests, coverage
#   2. Each service's env contract equals what gluon-local sets for it
#      (environments/local/<service>.values.yaml, plus its ports), read
#      from outside the harness
#   3. notification-service's world, held open around notification-service-rs
#      (its walking skeleton, built here). Seen from outside: the service ready,
#      and its own database migrated (so it got POSTGRES_*). What the harness
#      gave it, checked live but not yet used by the skeleton (it reads neither
#      Kafka nor the service URLs): a broker holding its four input topics, a
#      stub for user-service and one for order-service. Then torn down with no
#      process, directory or port left
#   4. Checks selected by service: every module in checks/ is marked for a
#      known service (today all user-service's); a run for each service
#      collects exactly the modules marked for it; an unknown service, and
#      notification-service without the Kafka jars, stop a run as a usage
#      error with the reason
#   5. user-service runs unchanged: every check green against user-service-rs,
#      with the same command line as gluon bin/verify-rust-spike (~10 min;
#      --skip-contract leaves it out)
# Each result is printed as it is found; the exit status is 0 only if all pass.
#
#   scripts/verify-multi-service-harness.sh [--skip-ci] [--skip-contract]
#
# Runs as the repo's owner. From the sandbox's root desktop terminal it
# re-runs itself as that user.
set -uo pipefail
SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")/.."
REPO="$PWD"
GLUON="$(realpath ../..)"

. "$(dirname "$SELF")/lib/owner.sh"
run_as_owner "$PWD" "$SELF" "$@"

SKIP_CI=0
SKIP_CONTRACT=0
for arg in "$@"; do
  case "$arg" in
    --skip-ci) SKIP_CI=1 ;;
    --skip-contract) SKIP_CONTRACT=1 ;;
  esac
done

passed=0
failed=0
ok() { echo "ok   $*"; passed=$((passed + 1)); }
bad() { echo "FAIL $*"; failed=$((failed + 1)); }
SCRATCH="$(mktemp -d /tmp/verify-multi-service-harness.XXXXXX)"
HOLDER_PID=""
cleanup() {
  [ -n "$HOLDER_PID" ] && kill -TERM "$HOLDER_PID" 2> /dev/null && wait "$HOLDER_PID" 2> /dev/null
  rm -rf "$SCRATCH"
}
trap cleanup EXIT
PYTHON="$REPO/.venv/bin/python"
NS_REPO="$GLUON/services/notification-service-rs"
NS_BIN="$NS_REPO/target/debug/notification-service"
port_open() { (exec 3<> "/dev/tcp/127.0.0.1/$1") 2> /dev/null; }
http_code() { curl -s -m 5 -o /dev/null -w '%{http_code}' "$@" || true; }
json() { "$PYTHON" -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1"; }
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

echo "== 1. CI (scripts/ci.sh) =="
if [ "$SKIP_CI" = 1 ]; then
  echo "skip --skip-ci given"
elif scripts/ci.sh > "$SCRATCH/ci.log" 2>&1; then
  ok "$(grep -Eo '[0-9]+ passed[^=]*' "$SCRATCH/ci.log" | tail -1 | sed 's/ *$//'), $(grep -Eo 'Total coverage: [0-9.]+%' "$SCRATCH/ci.log")"
else
  bad "scripts/ci.sh failed"
  tail -8 "$SCRATCH/ci.log" | sed 's/^/     /'
fi

echo "== 2. Each service's env contract is what gluon-local sets =="
# The variable names gluon-local's values file sets, plus the service's two ports
# (the chart sets those from its own values) and POSTGRES_PORT (gluon-local uses
# the default 5432; the harness's Postgres is on a free port), against the
# harness's service_env.
for service in user-service notification-service; do
  if out="$("$PYTHON" - "$service" "$GLUON/environments/local/$service.values.yaml" 2>&1 << 'PY'
import sys

import yaml

from gluon_contract.env_contract import Endpoints, service_env, variable_prefix

service, values = sys.argv[1], sys.argv[2]
with open(values, encoding="utf-8") as file:
    gluon_local = {entry["name"] for entry in yaml.safe_load(file)["env"]}
prefix = variable_prefix(service)
expected = gluon_local | {f"{prefix}_PORT", f"{prefix}_METRICS_PORT", "POSTGRES_PORT"}
endpoints = Endpoints(
    http_port=1, metrics_port=2, postgres_host="h", postgres_port=3, otlp_endpoint="o",
    kafka_bootstrap="k", service_urls={"user-service": "u", "order-service": "o"},
)
got = set(service_env(service, endpoints, base_env={}))
if got != expected:
    print(f"harness only: {sorted(got - expected)}; gluon-local only: {sorted(expected - got)}")
    sys.exit(1)
print(", ".join(sorted(got)))
PY
  )"; then
    ok "$service: $out"
  else
    bad "$service: $out"
  fi
done


echo "== 3. notification-service's world, held open around notification-service-rs =="
if (cd "$NS_REPO" && cargo build -q --locked) > "$SCRATCH/build.log" 2>&1 && [ -x "$NS_BIN" ]; then
  ok "notification-service-rs built: $NS_BIN"
else
  bad "notification-service-rs didn't build"
  tail -5 "$SCRATCH/build.log" | sed 's/^/     /'
fi
cat > "$SCRATCH/hold.py" << 'PY'
"""Holds one notification-service harness open until SIGTERM, describing it in a JSON file."""
import json, signal, sys, threading
from pathlib import Path
from gluon_contract.config import load_config
from gluon_contract.harness import Harness

command, cwd, info, root = sys.argv[1:5]
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
config = load_config(
    {"CONTRACT_TARGET_CMD": command, "CONTRACT_TARGET_CWD": cwd,
     "CONTRACT_SERVICE": "notification-service"},
    cwd=Path(root),
)
with Harness(config, work_root=Path(root)) as h:
    assert h.kafka is not None
    Path(info).write_text(json.dumps({
        "base_url": h.base_url, "work_dir": str(h.work_dir),
        "pg_port": h.postgres.endpoint.port,
        "target_pid": h.target._process.pid if h.target._process else 0,
        "env": h.target.env,
        "ports": [h.endpoints.http_port, h.endpoints.metrics_port, h.otlp.port,
                  h.postgres.endpoint.port, h.kafka.port, *(s.port for s in h.stubs.values())],
    }))
    stop.wait()
Path(info + ".stopped").write_text("ok")
PY
mkdir -p "$SCRATCH/world"
INFO="$SCRATCH/world.json"
"$PYTHON" "$SCRATCH/hold.py" "$NS_BIN" "$NS_REPO" "$INFO" "$SCRATCH/world" > "$SCRATCH/hold.log" 2>&1 &
HOLDER_PID=$!
for _ in $(seq 1 1200); do
  [ -s "$INFO" ] && break
  kill -0 "$HOLDER_PID" 2> /dev/null || break
  sleep 0.1
done
if [ ! -s "$INFO" ]; then
  bad "the harness didn't come up for notification-service; its output:"
  tail -20 "$SCRATCH/hold.log" | sed 's/^/     /'
else
  BASE_URL="$(json "$INFO" 'd["base_url"]')"
  WORK_DIR="$(json "$INFO" 'd["work_dir"]')"
  PG_PORT="$(json "$INFO" 'd["pg_port"]')"
  TARGET_PID="$(json "$INFO" 'd["target_pid"]')"
  PORTS="$(json "$INFO" '" ".join(map(str, d["ports"]))')"
  env_of() { json "$INFO" "d['env'].get('$1', '')"; }
  ok "harness up for notification-service: work dir $WORK_DIR"
  expect "notification-service-rs ready: GET /health/ready" 200 "$(http_code "$BASE_URL/health/ready")"
  PG_BIN="$("$PYTHON" -c 'import os; from gluon_contract.config import find_pg_bin; print(find_pg_bin(os.environ.get("CONTRACT_PG_BIN")))')"
  expect "its database: notification logs in to notification, where it migrated sent_email" \
    "notification notification sent_email" \
    "$("$PG_BIN/psql" -X -tA -c "select current_user || ' ' || current_database() || ' ' || to_regclass('sent_email')" \
      "host=127.0.0.1 port=$PG_PORT user=notification password=notification dbname=notification connect_timeout=5" 2> /dev/null)"
  # From here, addresses are the env the harness passed (its record, not the process's):
  # the skeleton doesn't read them yet, so these show what it was given, live.
  expect "given KAFKA_BOOTSTRAP_SERVERS: a broker holding the input topics" \
    "fulfilment-events order-events payment-events user-events" \
    "$("$PYTHON" - "$(env_of KAFKA_BOOTSTRAP_SERVERS)" << 'PY' 2> /dev/null
import sys
from kafka import KafkaAdminClient
admin = KafkaAdminClient(bootstrap_servers=sys.argv[1])
print(" ".join(sorted(t for t in admin.list_topics() if not t.startswith("__"))))
admin.close()
PY
    )"
  expect "given USER_SERVICE_URL: a stub answering GET /users/{id}" 200 \
    "$(http_code "$(env_of USER_SERVICE_URL)/users/11111111-1111-4111-8111-111111111111")"
  expect "given ORDER_SERVICE_URL: a stub with no order until a check scripts one" 404 \
    "$(http_code "$(env_of ORDER_SERVICE_URL)/orders/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")"
  [ "$(env_of USER_SERVICE_URL)" != "$(env_of ORDER_SERVICE_URL)" ] \
    && ok "given separate stubs for user-service and order-service" || bad "one stub for both services"

  kill -TERM "$HOLDER_PID"
  wait "$HOLDER_PID" 2> /dev/null
  HOLDER_PID=""
  [ -f "$INFO.stopped" ] && ok "the harness stopped cleanly" || bad "the harness didn't stop cleanly"
  [ ! -e "$WORK_DIR" ] && ok "work directory removed" || bad "$WORK_DIR left behind"
  kill -0 "$TARGET_PID" 2> /dev/null && bad "notification-service-rs ($TARGET_PID) still alive" \
    || ok "notification-service-rs ($TARGET_PID) gone"
  left="$(ps -A -o pid=,command= | TEXT="$WORK_DIR" awk 'index($0, ENVIRON["TEXT"])')"
  expect "no process left mentioning the work directory (Postgres, Kafka)" "" "$left"
  open_ports=""
  for port in $PORTS; do port_open "$port" && open_ports="$open_ports $port"; done
  expect "no port left listening (service, metrics, OTLP, Postgres, Kafka, two stubs: $PORTS)" "" "$open_ports"
fi

echo "== 4. Checks selected by service =="
# Each module's service, read from its source as CI's test does (check_markers)
if out="$("$PYTHON" - << 'PY' 2>&1
import sys
from pathlib import Path

from gluon_contract.check_markers import marker_problems, module_services

sources = {f"checks/{p.name}": p.read_text(encoding="utf-8") for p in sorted(Path("checks").glob("test_*.py"))}
problems = marker_problems(sources)
if problems:
    print("; ".join(problems))
    sys.exit(1)
by_service: dict[str, list[str]] = {}
for name, source in sources.items():
    for service in module_services(source) or ():
        by_service.setdefault(service, []).append(name.removeprefix("checks/test_").removesuffix(".py"))
print("; ".join(f"{service}: {', '.join(groups)}" for service, groups in sorted(by_service.items())))
PY
)"; then
  ok "every module in checks/ is marked for a known service: $out"
else
  bad "check modules without a known service: $out"
fi
# A run for each service collects exactly the modules marked for it (and, for
# user-service, the count section 5 expects green)
CHECKS="?"
for service in user-service notification-service; do
  uv run --no-sync pytest checks -p no:cacheprovider -q --collect-only --target-cmd /bin/true \
    --service "$service" > "$SCRATCH/collect-$service.txt" 2>&1
  if out="$("$PYTHON" - "$service" "$SCRATCH/collect-$service.txt" << 'PY' 2>&1
import sys
from pathlib import Path

from gluon_contract.check_markers import module_services

service, listing = sys.argv[1], Path(sys.argv[2]).read_text(encoding="utf-8")
ids = [line for line in listing.splitlines() if line.startswith("checks/") and "::" in line]
collected = {line.split("::")[0] for line in ids}
marked = {
    f"checks/{p.name}"
    for p in Path("checks").glob("test_*.py")
    if service in (module_services(p.read_text(encoding="utf-8")) or ())
}
if collected != marked:
    print(f"collected only: {sorted(collected - marked)}; marked only: {sorted(marked - collected)}")
    sys.exit(1)
print(f"{len(ids)} checks from {len(marked)} modules")
PY
  )"; then
    ok "a run for $service collects exactly its modules: $out"
    [ "$service" = user-service ] && CHECKS="${out%% *}"
  else
    bad "a run for $service: $out"
  fi
done
out="$(CONTRACT_SERVICE=order-service uv run --no-sync pytest checks -p no:cacheprovider -q --target-cmd /bin/true 2>&1)"
code=$?
if [ "$code" = 4 ] && grep -q "no profile for 'order-service' (it knows user-service, notification-service)" <<< "$out"; then
  ok "CONTRACT_SERVICE=order-service: usage error (exit 4) naming the known services"
else
  bad "CONTRACT_SERVICE=order-service: expected exit 4 naming the known services, got $code"
  tail -5 <<< "$out" | sed 's/^/     /'
fi
mkdir -p "$SCRATCH/suite"
cp checks/conftest.py "$SCRATCH/suite/conftest.py"
cat > "$SCRATCH/suite/test_neutral.py" << 'PY'
def test_ready(harness):
    assert harness.base_url
PY
out="$(CONTRACT_CDC_HOME="$SCRATCH/no-jars" uv run --no-sync pytest "$SCRATCH/suite" -p no:cacheprovider -q \
  --service notification-service --target-cmd "$NS_BIN" 2>&1)"
code=$?
if [ "$code" = 4 ] && grep -q "notification-service needs a Kafka broker: no Kafka jars in $SCRATCH/no-jars/kafka" <<< "$out"; then
  ok "notification-service without the Kafka jars: usage error (exit 4) saying where they were looked for"
else
  bad "notification-service without the Kafka jars: expected exit 4 naming the jars, got $code"
  tail -5 <<< "$out" | sed 's/^/     /'
fi

echo "== 5. user-service runs unchanged =="
US_REPO="$GLUON/services/user-service-rs"
if [ "$SKIP_CONTRACT" = 1 ]; then
  echo "skip --skip-contract given"
else
  if (cd "$US_REPO" && cargo build -q --locked -p user-service -p events-probe) > "$SCRATCH/us-build.log" 2>&1 \
    && { [ -f "$US_REPO/target/asyncapi-docs/index.html" ] || (cd "$US_REPO" && scripts/asyncapi-html.sh) >> "$SCRATCH/us-build.log" 2>&1; }; then
    ok "user-service-rs and events-probe built, AsyncAPI HTML rendered"
  else
    bad "user-service-rs build failed"
    tail -5 "$SCRATCH/us-build.log" | sed 's/^/     /'
  fi
  # As bin/verify-rust-spike's contract step runs it: no --service, the default.
  uv run --no-sync pytest checks -p no:cacheprovider -rA --tb=line -q \
    --target-cmd "$US_REPO/target/debug/user-service" --target-cwd "$US_REPO" \
    --target-name user-service-rs --probe-cmd "$US_REPO/target/debug/events-probe" > "$SCRATCH/contract.log" 2>&1
  code=$?
  green="$(grep -cE '^PASSED checks/' "$SCRATCH/contract.log")"
  red="$(grep -cE '^(FAILED|ERROR) checks/' "$SCRATCH/contract.log")"
  if [ "$code" = 0 ] && [ "$red" = 0 ] && [ "$green" = "$CHECKS" ]; then
    ok "every user-service check green against user-service-rs: $green/$CHECKS"
  else
    bad "user-service checks: $green/$CHECKS green, $red red (exit $code)"
    grep -E '^(FAILED|ERROR) checks/' "$SCRATCH/contract.log" | head -20 | sed 's/^/     /'
  fi
fi

echo
if [ "$failed" = 0 ]; then
  echo "PASS: $passed checks"
else
  echo "FAIL: $failed of $((passed + failed)) checks failed"
  exit 1
fi
