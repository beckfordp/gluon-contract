# Plan — the harness for more than one service (gluon PLAN.md RPN-3)

Track `multi-service-harness_20261112`; spec: [`spec.md`](./spec.md).
Done when gluon `bin/verify-complete-RPN-3.sh` prints PASS.

## Phase 1: Service profiles and the env contract [checkpoint: 8791942]

- [x] Task: Write failing tests for the service profiles (`services.py`):
      user-service needs nothing more; notification-service a broker with its
      four input topics, and calls user-service and order-service; an unknown
      service has no profile `011e91d`
- [x] Task: Implement `services.py` `011e91d`
- [x] Task: Write failing env contract tests: notification-service gets
      exactly its variables (`KAFKA_BOOTSTRAP_SERVERS`, `USER_SERVICE_URL`,
      `ORDER_SERVICE_URL` besides the common ones); a missing broker or
      called-service address is an error; user-service's is unchanged `91a346a`
- [x] Task: Implement them in `env_contract.py` (`Endpoints` gains the broker
      and the called services' URLs) `91a346a`
- [x] Task: Write failing config tests: `CONTRACT_SERVICE` must name a
      profile; a service that needs a broker needs the CDC jars
      (`CONTRACT_CDC_HOME`), checked up front `3b15d7b`
- [x] Task: Implement them in `config.py` `3b15d7b`
- [x] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md) `8791942`

## Phase 2: The harness starts each service's dependencies [checkpoint: 1f35c65]

- [x] Task: Write failing tests: `KafkaBroker.create_topics`; the harness,
      run for notification-service against the stand-in, hands it a live
      broker with the topics and a stub per called service, and tears all of
      it down (also when the broker can't start) `ce72d21`
- [x] Task: Implement them in `cdc.py` and `harness.py` `ce72d21`
- [x] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md) `1f35c65`

## Phase 3: Checks selected by service [checkpoint: c4f6bb8]

- [x] Task: Write failing pytester tests: `--service` selects the checks
      marked for it and deselects the others; unmarked checks run for any
      service; an unknown service is a usage error `e7d5511`
- [x] Task: Implement the `service` marker, `--service` and the selection in
      `pytest_plugin.py`; mark every check module `user-service` `e7d5511`
- [x] Task: `scripts/verify-multi-service-harness.sh`; README and
      tech-stack updated `7154cfc`
- [x] Task: Conductor - User Manual Verification 'Phase 3' (Protocol in workflow.md) `c4f6bb8`

## Review

- **In the session** (`271c1b7`): a shallow self-review of the `src/` diff
  only, the tests not read. It changed two small things: the report header
  asks `run_service` for the run's service, and `KAFKA_VARIABLE` is
  documented. The session also skipped `workflow.md`'s approval points: the
  plan, each commit and each phase checkpoint went ahead without the user.
- **After the session**: the user reviewed the track step by step (the spec,
  each task, each checkpoint). That review found comments R1–R24; the must and
  should fixes (R5–R11, R13, R16, R18) are track
  [`rpn3-review-fixes_20261112`](../rpn3-review-fixes_20261112/),
  the user waived the rest as minor, and approved the fixes (2026-11-12). The
  phase notes record the user's approval.
