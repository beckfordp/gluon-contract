# Plan — the source guard reads a whole citation (gluon RPN-10 follow-up)

`gluon_contract.check_sources.cited_files` reads a check's `Source:` paragraph for
`capture <file>, <file> and <file>` and CI checks each file exists (TD-41). A
remark in brackets inside the list stops it: `capture CAPTURE.sh (user-events),
db/sent-email.jsonl` yields only `CAPTURE.sh`, and the guard passes without
checking the rest. Found in RPN-10 (its first drafts passed citing one file of
four). Agreed with the owner 2026-11-17.

## Phase 1: Remarks in brackets don't end a citation
- [x] 1.1 Tests first (`tests/unit/test_check_sources.py`): a bracketed remark between
      or after names is skipped, the list read on past it; a file named only inside
      a remark isn't cited; nested brackets; existing forms unchanged
- [x] 1.2 `cited_files`: a remark in brackets (one level of nesting) may follow any
      name in the list, which goes on past it; names inside a remark aren't cited; a
      citation written inside brackets (`ADR 0025 (capture http/a.txt)`) still counts
- [x] 1.3 Every check module's citations re-read: any file the fix newly finds
      cited but missing from its capture is fixed (the citation or the check), listed
      for the owner (none: no check's citations change)
- [x] 1.4 `scripts/ci.sh` green (419 passed, coverage 95.54%)

## Phase 3: Review findings fixed (RPN-10 and this track; owner, option a)
- [x] 3.1 M1: the user-events checks cite the capture and gluon's documented contracts
      (docs/system-design.md "Envelope", "Consume-time lookups (ADM-3)"; ADR 0010),
      not Scala production classes
- [x] 3.2 M2: the capture's own ids are a recorded exception (the check module's
      docstring; `product-guidelines.md` "Test data")
- [x] 3.3 M3: `KafkaBroker.records_now` reads a topic to its end offset, no settle wait
      (integration test); the user-events checks read the DLQ with it
- [x] 3.4 **(gluon)** the Low findings recorded: TECHNICAL_DEBT.md TD-S11 to TD-S18
- [x] 3.5 `scripts/ci.sh` green (420 passed, coverage 95.52%); the user-events group
      still all pending (6)

## Phase 2: Review, then archive
- [x] 2.1 Review of the track's changes against the plan, `product-guidelines.md`
      and the style guides; report to the owner
- [x] 2.2 Archive once the owner approves (approved 2026-11-17)
