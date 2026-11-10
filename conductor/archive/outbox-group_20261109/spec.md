# Spec — RUST-1.6: Outbox and envelope group

`checks/test_outbox.py` (gluon PLAN.md RUST-1.6; ADR 0028 "Outbox and
envelope" row). Reference: ADR 0008/0009, `docs/system-design.md` (envelope,
`correlationId` = userId for `user-events`), `registry/user-service/registry.json`
(payload schema, latest version), the registered connector config in
`infra/k8s/local-infra/debezium-connectors-register.yaml`, capture
`db-outbox-events.jsonl`.

Checks: one outbox row per successful signup (none for 409 or 400);
`aggregate_id` and `correlation_id` are the userId; the envelope has exactly
`eventId` (a UUID, not the row id), `eventType` `UserRegistered`, `timestamp`
(an instant as Java prints it, within seconds of the account's creation),
`source` `user-service`, `correlationId`, `payload`; the payload validates
against the registry; routed as the connector routes it: topic `user-events`,
key the userId, value the envelope, headers `traceparent` (W3C) and
`correlation_id`.

Helpers (unit-tested): connector routing from the config file, registry schemas.
Acceptance: CI green; `scripts/verify-outbox-group.sh` PASS (red until RUST-3.1).
