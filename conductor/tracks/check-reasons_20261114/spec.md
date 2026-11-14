# Spec: Full failure reasons in check output (TD-40)

## Overview
`verify-check-group.sh` prints each check's outcome from pytest's `-rA` summary, which
cuts messages to the terminal width (`red  test_… - A...`). It already writes a junit
report (RPN-4). This track reads outcomes and reasons from that report instead, in a
tested module.

## Functional Requirements
- FR-1: `gluon_contract/check_report.py` reads a junit report into one outcome per
  check:
  - its name, with parameters (e.g. `test_x[HEAD-emails-head]`)
  - its state: passed, failed, error or skipped
  - its reason: the failure or error message
- FR-2: The lines:
  - a red check is `red  <name> - <reason>`, with the reason on one line
    (whitespace collapsed) and cut at 200 characters with `…`
  - a passing check is `pass <name>`
  - a skipped check prints nothing, as today
- FR-3: The `--expect-red PATTERN` judgement moves into the module, with the same
  meaning:
  - it passes when every check failed (none passed, errored or skipped) and each
    failure's message or text contains PATTERN
  - otherwise it lists each offender
- FR-4: `verify-check-group.sh` runs `python -m gluon_contract.check_report` for the
  lines and counts, and for `--expect-red`. The inline heredoc goes, and the `-rA`
  summary is no longer parsed. Output and exit codes are otherwise unchanged.
- FR-5: A missing or unreadable report is a failure naming it, not an empty pass.

## Non-Functional Requirements
- Red first: unit tests against small junit XML samples (a long assert message, a
  multi-line one, an error, a skip, a parametrised name).
- `scripts/ci.sh` green; coverage at least 80%.

## Acceptance Criteria
- `verify-check-group.sh checks/test_notification_rest.py --service
  notification-service`, against notification-service-rs: the 19 `/emails` lines each
  show their reason in full (`… 404 …`) instead of `- A...`, and the other 5 are green.
- `--expect-red 404` keeps today's behaviour. The fail path is shown live: that group,
  run with it, fails and names the 5 passing checks. The pass path is shown by a unit
  test.
- `--expect-green` against user-service's REST group is unchanged.

## Out of Scope
- TD-41 (citations beyond `http/…`).
- Changing `bin/verify-port`'s own outcome parsing.
