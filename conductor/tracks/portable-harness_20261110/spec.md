# Spec: Portable harness — macOS and Linux (Ubuntu)

## Overview
The harness's tests and `scripts/verify-*.sh` were written in the sandbox (Ubuntu, often root) and assume Linux. On the Mac, 16 integration tests fail and `verify-isolated-runner.sh` stops at line 28. The harness code itself (`src/`) is portable; the Linux-only parts are in test doubles and scripts. Make both run on macOS and Ubuntu, with the same results.

## Functional Requirements
1. **Shared owner helper** `scripts/lib/owner.sh`, used by all 7 verify scripts with the "run as the repo's owner" opening (check-group, cluster-mode, implicit-behaviours, isolated-runner, probe-group, probe-stubs, cdc-group):
   - repo owner: GNU `stat -c %U`, else BSD `stat -f %Su`
   - owner's home: `getent passwd`, else the shell's `~owner`
   - root re-exec via `runuser` kept (Linux sandbox only, still guarded by `command -v runuser`)
   - `verify-cdc-group.sh:12` (`getent` called unconditionally) uses it too
2. **Exact env capture without /proc:** the stand-in target is launched through a small `sh` wrapper that writes `env -0` to a file, then `exec`s Python; `stand_in_target.started_with()` reads that file. This keeps the existing guarantee: no `LC_CTYPE` added by Python (PEP 538).
3. **Process listing without /proc:** `tests/integration/processes.py` uses `ps -A -o pid=,command=` (works with both procps and BSD ps).
4. **`pgrep -af`** in `verify-isolated-runner.sh` replaced with a form that means the same on both (`-a` means "show the command line" on Linux but "include ancestors" on macOS).
5. **CI:** add `macos-latest` beside `ubuntu-latest` in `.github/workflows/ci.yml`; the macOS job installs `postgresql@16` from Homebrew and sets `CONTRACT_PG_BIN`.
6. A final sweep of `scripts/` and `tests/` for any other GNU/Linux-only use, fixed the same way.

## Non-Functional Requirements
- No GNU coreutils needed on macOS; nothing Linux-only added.
- Behaviour on Ubuntu unchanged: the same checks, the same messages.
- No change to `src/gluon_contract` unless the sweep finds something there.

## Acceptance Criteria
- On macOS (Homebrew uv + postgresql@16, no coreutils on the PATH): `scripts/ci.sh` green (0 failed) and `verify-isolated-runner.sh` passes all its checks.
- Every `verify-*.sh` gets past its opening on macOS, then passes or fails only for reasons outside this track (e.g. a target not built, gluon-local not up).
- GitHub Actions green on both ubuntu-latest and macos-latest.
- Still green in the sandbox (Ubuntu, including the root re-exec path).

## Out of Scope
- Windows.
- The cargo-audit findings in user-service-rs.
- gshop's Node 26 vitest issue.
- RUST-5.x laptop-pass work.
