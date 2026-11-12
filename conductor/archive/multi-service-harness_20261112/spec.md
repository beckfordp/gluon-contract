# Spec — the harness for more than one service (gluon PLAN.md RPN-3)

## Why
The harness was written for one service, user-service: the service name was
already a setting (`CONTRACT_SERVICE`), but only the variable names followed
it. notification-service, the second Rust port (gluon ADR 0029), reads more
than user-service does: a Kafka broker and the two services it calls. Its
check groups arrive one session at a time (RPN-4 on), each written here and
seen failing first, so the harness must first be able to start it, with its
env contract, and run only its checks.

## Reference
- notification-service `src/main/resources/application.conf`: the `${?VAR}`
  overrides (`NOTIFICATION_SERVICE_PORT`, `NOTIFICATION_SERVICE_METRICS_PORT`,
  `POSTGRES_*`, `KAFKA_BOOTSTRAP_SERVERS`, `USER_SERVICE_URL`,
  `ORDER_SERVICE_URL`) and the `notification` database login
- gluon `environments/local/notification-service.values.yaml`: what
  gluon-local sets (the same list, with OTLP)
- the capture `contracts/notification-service/20261111/CAPTURE.sh`: the four
  input topics created before the service starts; user-service and
  order-service stood in for over HTTP
- user-service's contract is unchanged (`env_contract.py`, RUST-1.2 FR2)

## Functional requirements
- **FR1 The service is a parameter.** `--service` (`CONTRACT_SERVICE`),
  default `user-service`. A name the harness has no profile for is a
  configuration problem, reported with the others, naming the known services.
- **FR2 A profile per service.** What a service needs besides Postgres and the
  OTLP stub: a Kafka broker (and the topics to create on it), and the services
  it calls. user-service: nothing more. notification-service: a broker with
  `user-events`, `order-events`, `payment-events`, `fulfilment-events`; calls
  user-service and order-service.
- **FR3 The env contract per service.** `<DOMAIN>_SERVICE_PORT`,
  `<DOMAIN>_SERVICE_METRICS_PORT`, `POSTGRES_*` (the domain login),
  `OTEL_EXPORTER_OTLP_ENDPOINT` for every service (unchanged); plus
  `KAFKA_BOOTSTRAP_SERVERS` when it needs a broker, and
  `<CALLED_DOMAIN>_SERVICE_URL` for each service it calls. Nothing else; the
  minimal base passes through as before.
- **FR4 The harness starts what the profile asks for.** Postgres, the OTLP
  stub, then the broker (the CDC stack's Kafka jars, topics created), then a
  scriptable HTTP stub per called service, then the target; torn down in
  reverse, also when a start fails. The jars are checked at configuration
  time, only for a service that needs a broker.
- **FR5 Checks belong to a service.** A check module marked
  `pytest.mark.service("<name>")` runs only when the run is for that service;
  the others are deselected (not skipped: they aren't this run's contract).
  Unmarked checks are service-neutral. Every existing check module is marked
  `user-service`.
- **FR6 user-service runs unchanged.** The same command line
  (`bin/verify-rust-spike --only build contract`) gives 128/128 green
  (127/127 since 2026-11-12: the probe's slow-lookup timing check dropped,
  `b261c29`; timing isn't contract).

## Out of scope
- Any notification-service check group (RPN-4 on), and the stubs' answers
  those groups need (the capture's users and orders): the stubs start with
  `HttpStub`'s defaults and are scripted by the checks that use them.
- Cluster mode for notification-service.
- Any change to a contract or to the Rust ports.

## Done when
gluon `bin/verify-complete-RPN-3.sh` prints PASS: `scripts/ci.sh` green;
user-service's 128 checks green (127 since 2026-11-12); a `notification` env contract unit test in
`tests/unit/test_env_contract.py`; this track archived; nothing uncommitted.
