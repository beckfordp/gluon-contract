# Spec: Implementation switch resets Debezium's slot too (gluon RUST-5.2)

## Overview
gluon `bin/k8s-local-up`'s user-service switch drops the `public` schema and
`dbz_publication`, then restarts `user-outbox-connector`. The `debezium_user` slot
survives. The new service's migrations write DML after the drop. On restart, pgoutput
decodes from the slot's old position against the catalog of that time, fails with
"publication dbz_publication does not exist", and CDC stays down. The rehearsal
`test_after_a_schema_reset_and_a_connector_restart_rows_flow_again` misses it because
it writes no DML between the reset and the restart.

## Functional Requirements
- FR-1: The switch SQL lives in one gluon file,
  `infra/k8s/local-infra/user-switch-reset.sql`. `bin/k8s-local-up` and the rehearsal
  both run that file.
- FR-2: The rehearsal writes migration-history DML between the reset and the connector
  restart, as a new service's migrations do.
- FR-3: The reset also ends the slot's walsender and drops `debezium_user`, so Debezium
  creates a fresh slot on restart.

## Acceptance Criteria
- Red: the rehearsal, run against the file holding today's three statements, fails 3/3.
- Green: with FR-3, it passes 3/3. `scripts/ci.sh` passes.
- Live, in gluon: switch scala→rust→scala with no manual recovery, and
  `bin/run-acceptance` passes 53/53 each way.

## Out of Scope
- OrbStack restarts losing connectors; the US-9.5 flake (separate TD items).
