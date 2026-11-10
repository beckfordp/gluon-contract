# Plan — Portable harness: macOS and Linux (Ubuntu)

## Phase 1: Shared owner helper [checkpoint: 9000dc1]
- [x] Task: write failing tests `tests/unit/test_owner_sh.py`: source `scripts/lib/owner.sh` in bash and check `repo_owner` (matches `id -un` for a dir we own), `owner_home` (matches `$HOME`), with a stand-in `stat` and `getent` on the PATH to force each branch (GNU stat / BSD stat / no getent) `1ba098a`
- [x] Task: implement `scripts/lib/owner.sh`: `repo_owner <dir>`, `owner_home <user>`, `reexec_as_owner <dir> "$@"` (the `runuser` root path, unchanged in behaviour) `d4057ca`
- [x] Task: switch the 7 scripts (check-group, cluster-mode, implicit-behaviours, isolated-runner, probe-group, probe-stubs, cdc-group) to the helper; `verify-cdc-group.sh:12` home lookup via `owner_home` `6722a73`
- [x] Task: start `scripts/verify-portable-harness.sh`: section 1 checks each script's opening runs on this OS (no `stat`/`getent` errors) and that no script still calls `stat -c`/`getent` directly `95dbb36`
- [x] Task: Conductor - User Manual Verification 'Phase 1: Shared owner helper' (Protocol in workflow.md)

## Phase 2: Test doubles and process checks without /proc [checkpoint: cb6d15b]
- [x] Task: failing test: `started_with()` in a process started with a known environment (C locale) returns exactly it, with no `LC_CTYPE` added (red on macOS today) `c544854`
- [x] Task: implement `started_with()`: `/proc/self/environ` on Linux, `sysctl` `KERN_PROCARGS2` (ctypes) where there is no `/proc` *(2026-11-10: replaces the `sh` wrapper, which adds PWD/SHLVL/_)* `e3806fd`
- [x] Task: failing test for `processes_mentioning()` parsing `ps -A -o pid=,command=` output (incl. its own pid excluded); implement `7da321f`
- [x] Task: replace `pgrep -af` in `verify-isolated-runner.sh` with a portable form (`pgrep -f` for pids, `ps` for command lines) `8357026`
- [x] Task: extend the verify script: section 2 runs the integration tests (0 failed) and `verify-isolated-runner.sh --skip-ci` (all ok) `9114ce2`
- [x] Task: Conductor - User Manual Verification 'Phase 2: Test doubles and process checks without /proc' (Protocol in workflow.md)

## Phase 3: Sweep, CI on both OSes
- [x] Task: sweep `scripts/` and `tests/` for remaining GNU/Linux-only use (`sed -i`, `readlink -f`, `date -d`, `timeout`, `ps`/`pgrep` flags, `xargs -r`, `grep -P`, `/proc`, `/sys`); fix any, each with a test where testable — nothing further found
- [ ] Task: CI: add `macos-latest` to the matrix in `.github/workflows/ci.yml`; on macOS `brew install postgresql@16` and set `CONTRACT_PG_BIN`
- [ ] Task: extend the verify script: section 3 runs `scripts/ci.sh`, then every `verify-*.sh` past its opening, reporting each one's result
- [ ] Task: push the branch, open a PR to main to trigger CI; confirm both jobs green
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Sweep, CI on both OSes' (Protocol in workflow.md)
