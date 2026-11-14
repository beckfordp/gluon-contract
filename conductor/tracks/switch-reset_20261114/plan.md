# Plan — Implementation switch resets Debezium's slot too (gluon RUST-5.2)

Phase verification: spec acceptance commands, run and shown.

## Phase 1: Red
- [x] Task: The rehearsal runs gluon's switch file and writes migration DML before restart cc19e6c
    - [x] gluon `infra/k8s/local-infra/user-switch-reset.sql` with today's three statements
    - [x] Test reads it (path like `routing.CONNECTORS_FILE`), runs it with `psql -f`
    - [x] Migration-history table + row between recreate and `restart_connector()`
    - [x] Run 3×: fails each time
    - [x] Also: wait for a committed offset first. Without one, the restart snapshots afresh
          past the bad WAL, which is why the first red attempt passed 3/3
    - *Red 3/3: 'no matching record on user-events after 90s', the pre-switch row seen.*

## Phase 2: Green
- [x] Task: The reset drops the stale slot cc19e6c
    - [x] Terminate `debezium_user`'s `active_pid`, drop the slot (wait if active)
    - [x] Rehearsal 3× green; `scripts/ci.sh` green
    - *Green 3/3, a fresh slot created on restart, no 'does not exist'; ci.sh 360 passed,
      95.13%. The SQL itself is gluon's file (committed there, with approval).*
- [x] Task: gluon `bin/k8s-local-up` runs the file (gluon commit, approved) gluon 026401b
- [x] Task: Live switch both ways, acceptance 53/53 each; RUST-5.2 note in gluon plan gluon 026401b
    - *Rust→Scala→Rust, no manual recovery, 53/53 each way. gluon `bin/verify-laptop-prep`
      also checks the slot drop (22/22).*

## Phase: Review Fixes
- [x] Task: Apply review suggestions 31c3d26
