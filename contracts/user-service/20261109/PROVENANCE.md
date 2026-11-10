# Provenance — user-service capture 20261109

Produced on the laptop by the user with the commands in
[`../CAPTURE.md`](../CAPTURE.md) (ADR 0028 decision 2: Scala-generated
artifacts and behaviour nothing documents, captured on request), uploaded to
the sandbox as `user-service-contracts-20261109.tar.gz` and committed here
unchanged, except that macOS AppleDouble files (`._*`) were dropped and
`PROVENANCE.txt` became this file.

## As recorded by the capture (PROVENANCE.txt, verbatim)

```
user-service commit: 294dcf6d13333f57464fb049fb8ac548beb2fb72
dirty: 0 files
captured: 2026-11-09T18:41:40Z
openjdk version "25.0.3" 2026-04-21 LTS
node: v26.13.0
```

## Notes

- JDK 25 on the laptop; the service's build targets JDK 21. Nothing in the
  captures depends on the JDK beyond stderr warnings in `stdout.log`.
- The local Docker Postgres was recreated empty for the capture
  (`docker compose down -v`), so every account, token and hash here is a
  throwaway from a database that no longer exists.
- Captured at user-service commit `294dcf6`, clean working tree.
