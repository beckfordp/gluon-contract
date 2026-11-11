# Provenance — notification-service capture 20261111

Produced on the laptop by `CAPTURE.sh` (this directory; ADR 0029, the
notification-service port): the Scala service staged and run against fresh
Kafka and Postgres containers and `stub.py`, every consumer path driven.

```
notification-service commit: b60d4d78c547ce382fd4c9da2a4c56dab0c2fda5
dirty: 0 files
captured: 2026-11-11T11:17:12Z
openjdk version "25.0.3" 2026-04-21 LTS
kafka image: apache/kafka:3.8.0; postgres image: postgres:16
```

## Notes

- Kafka and Postgres were created empty for the capture and removed after,
  so every row, offset and id here is throwaway example data.
- The users and orders are `stub.py`'s fixtures (`example.com` addresses).
- The DLQ records under `kafka/` are the capture's deliberate failure
  paths (undecodable envelopes and payloads, the always-500 user lookup),
  not faults.
