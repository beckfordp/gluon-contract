# Spec — RUST-1.5: Schema and stored-format group

## Overview
`checks/test_schema.py` (gluon PLAN.md RUST-1.5; ADR 0028 decision 5 and the
"Schema and stored formats" row). Reference: the Scala service's migration
files (`services/user-service/src/main/resources/db/migration/V*.sql`) applied
to an empty database, the capture's stored rows (`db-user-account.txt`,
`db-auth-tokens.txt`) and ADR 0028 decision 5.

## Functional Requirements
1. **Schema snapshot (helper):** tables, columns (type, nullability, default),
   constraints (kind, definition, name) and indexes of the `public` schema,
   migration history tables excluded (`flyway_schema_history`,
   `_sqlx_migrations`); a pure diff listing every difference.
2. **Checks:** the service's schema equals the Scala migrations' (applied to a
   fresh database in the same cluster, `CONTRACT_REFERENCE_MIGRATIONS`
   overrides the path); passwords stored as `pbkdf2$210000$<salt>$<hash>` that
   verify independently; a Scala-made hash (capture) logs in; tokens stored
   only as SHA-256 hex, access on signup, access and refresh on login, with
   1 h / 30 d lifetimes; no plaintext password in any column.

## Acceptance Criteria
- `scripts/ci.sh` green; `scripts/verify-schema-group.sh` PASS (group red until
  RUST-2.4/2.5)
