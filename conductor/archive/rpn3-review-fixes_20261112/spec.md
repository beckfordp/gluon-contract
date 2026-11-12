# Spec — fixes from the review of the multi-service harness (gluon PLAN.md RPN-3)

## Why
Track `multi-service-harness_20261112` (archived) was built in one pass,
without the approval points `workflow.md` sets. The user then reviewed it
step by step; these are the review comments judged must or should fix. The
rest of the list (R1–R4, R12, R14, R15, R17, R19–R23) is reviewed after this
track.

## Review comments fixed here
Must:
- **R5** `HttpStub` answers an unscripted request for any path but
  `/users/{id}` with 200 and an empty body: the order-service stub "finds"
  every order. **R11** the verify script expects that 200.
- **R16** an unmarked check module is service-neutral, so a
  notification-service module that forgets its marker runs (and fails) in
  user-service's runs; **R18** verify section 4 accepts only the
  `user-service` marker, so it fails once notification-service's first module
  arrives.
- **R6** the harness test asks the user-service stub for `/users/<port
  number>` and doesn't check for 200.
- **R10** verify section 3 compares two values from the harness's own record
  ("KAFKA_BOOTSTRAP_SERVERS is the broker") and calls the section "probed from
  outside".
- **R9** the archived plan's "Review" section overstates the review made in
  the session.

Should:
- **R8** `create_topics` doesn't retry while the broker isn't ready, and
  fails if a topic appears between listing and creating.
- **R13** nothing tests that the `service` marker is registered (the
  pytester suites don't run with `--strict-markers`).
- **R7** the topic test's one-partition check holds for any topic (the
  broker's default is one partition), so it proves nothing about
  `create_topics`.

## Decisions (the user, 2026-11-12)
- R5: option (a): unscripted, any path but `/users/{id}` answers 404, empty.
  The capture's users and orders (`ns_scenarios`) come with the checks that
  need them (RPN-4 on).
- Tracked here, not by reopening the archived track.
- R9: the archived plan's review section is replaced by an accurate one
  pointing here; the phase notes are updated as the user approves each phase.
- One stop per fix: diff and test output shown, committed on the user's okay.

## Not fixed (the user, 2026-11-12)
R1–R4, R12, R14, R15, R17, R19–R23 were minor and are left as they are. R24 (a
timing check in user-service's probe group) was fixed here by removing the
check: timing isn't contract; user-service's contract is 127 checks.

## Done when
Every task below committed with the user's approval; `scripts/ci.sh` and
`scripts/verify-multi-service-harness.sh` pass; gluon
`bin/verify-complete-RPN-3.sh` still prints PASS.
