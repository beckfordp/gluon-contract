# Plan — Full failure reasons in check output (TD-40)

Phase verification: the spec's acceptance commands, run and shown. No verify script
(TD-46 rule).

## Phase 1: The report module and the script
- [x] Task: Record the baseline
    - [x] `verify-check-group.sh checks/test_notification_rest.py --service
          notification-service`: the red lines, cut as they are today (`- A...`)
    - *Baseline 2026-11-14 (tests/contract `7871f51`'s run): worse than cut, the 19 red
      lines carry no reason at all (`red  test_emails_lists_every_email_newest_first`);
      5 green.*
- [ ] Task: `check_report` reads outcomes from junit
    - [ ] Red: `tests/unit/test_check_report.py`, with junit samples: passed, failed
          (a long message, a multi-line one), error, skipped, a parametrised name; and
          a missing or garbled report raising an error that names the file
    - [ ] `Outcome(name, state, reason)`, `outcomes(path)`, and `line(outcome)` (200
          characters, whitespace collapsed, `…`)
- [ ] Task: The `--expect-red` judgement in the module
    - [ ] Red: tests where every check failed with the pattern → ok; one passing, one
          erroring, one skipped and one failing without it → each named, with the
          messages today's heredoc gives
    - [ ] `expect_red(outcomes, pattern) -> list[str]`, the problems
- [ ] Task: CLI and the script
    - [ ] `python -m gluon_contract.check_report lines <report>` prints the lines and
          a final `green=N red=M`
    - [ ] `expect-red <report> <pattern>` prints the problems, or `N red`; exit 1 on
          problems; a usage error otherwise (unit-tested through `main(argv)`)
    - [ ] `verify-check-group.sh` uses both; the heredoc and the `-rA` parsing go
          (`-rA` stays only if the log still needs it)
- [ ] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md)
    - [ ] The notification group against Rust: 19 red lines with full reasons, 5 green
    - [ ] `--expect-red 404` on it: FAIL, naming the 5 passing checks (the fail path,
          live)
    - [ ] `checks/test_user_rest.py --service user-service --expect-green`: PASS, as
          before
    - [ ] `scripts/ci.sh` green
- [ ] Task: Tick TD-40.1 in gluon `TECHNICAL_DEBT.md` (needs approval)
