# Spec — RUST-1.3: REST group

## Overview
`checks/test_rest.py`: user-service's REST contract as executable checks
(gluon PLAN.md RUST-1.3, ADR 0028 "Contracts the harness checks", REST row).
Written from the reference (ADR 0028 decision 2) — capture
`contracts/user-service/20261109` (`http/*.txt`), its OpenAPI descriptions,
ADR 0028's documented edge cases — never from the Rust code. Each check names
its source. Written before the Rust items that satisfy them (RUST-2.4–2.6), so
they are first seen failing against today's build, which only serves `/health`.

## Functional Requirements
1. **Helpers (pure, unit-tested):** `http.py` (a raw `http.client` request:
   exact method, headers — including none — and body; case-insensitive header
   access, comma-list headers as sets), `capture.py` (parse `curl -si`
   captures), `formats.py` (Java `Instant.toString` formatting of a
   timestamp, the token/UUID shapes, PBKDF2 verification with `hashlib`,
   SHA-256 hex).
2. **Checks**, each against the session harness:
   - signup: 201 shape; email normalisation (trim, Unicode lower-case); 409
     after normalisation; invalid email and short password 400s; UTF-16
     password length (`😀😀😀😀` accepted, `ééééééé` refused); U+00A0 kept
     in the address (a different account from the plain one); content type not
     checked (`text/plain`, none → 201)
   - login: 200 shape with the signup's userId; email normalised; wrong
     password and unknown email the same 401 body; empty password, invalid
     email 400s; an unknown email takes comparable time to a wrong password
   - `GET /users/{id}`: 200 shape with `createdAt` as Java prints the stored
     instant; an uppercase id answered in lower case; 404 body; 400 for a
     malformed id
   - framework errors: malformed JSON, missing field, wrong types, empty body
     → 400 `text/plain; charset=UTF-8` starting `Invalid value for: body (`
     (the user's 2026-11-09 decision: the bracketed detail is the JSON
     library's own wording); wrong method → 405 `Method Not Allowed`; unknown
     path → 404 `Not found`
   - CORS: preflight headers and simple-request headers, compared as sets
   - health: `/health` and `/health/ready` 200 with empty bodies and no
     Content-Type; `/health/ready` 503 while Postgres is stopped
3. **Rules:** JSON bodies compare exactly (as parsed JSON); `Content-Type`
   compares exactly; every check's docstring has a `Source:` line.

## Acceptance Criteria
- `scripts/ci.sh` green (helpers unit-tested)
- `scripts/verify-rest-group.sh`: CI green; every check names its source; the
  group runs against the Rust build and its results are reported per check
  (red until RUST-2.4–2.6; green is RUST-2.6's exit criterion)
