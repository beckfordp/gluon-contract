# Plan — Implementation switch resets Debezium's slot too (gluon RUST-5.2)

Phase verification: spec acceptance commands, run and shown.

## Phase 1: Red
- [ ] Task: The rehearsal runs gluon's switch file and writes migration DML before restart
    - [ ] gluon `infra/k8s/local-infra/user-switch-reset.sql` with today's three statements
    - [ ] Test reads it (path like `routing.CONNECTORS_FILE`), runs it with `psql -f`
    - [ ] Migration-history table + row between recreate and `restart_connector()`
    - [ ] Run 3×: fails each time

## Phase 2: Green
- [ ] Task: The reset drops the stale slot
    - [ ] Terminate `debezium_user`'s `active_pid`, drop the slot (wait if active)
    - [ ] Rehearsal 3× green; `scripts/ci.sh` green
- [ ] Task: gluon `bin/k8s-local-up` runs the file (gluon commit, approved)
- [ ] Task: Live switch both ways, acceptance 53/53 each; RUST-5.2 note in gluon plan
