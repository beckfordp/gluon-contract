<!-- SPDX-License-Identifier: MIT -->

# Contract captures

Each `<service>/<date>/` is one laptop capture of a Scala service's behaviour
(ADR 0028 decision 2), committed as it came back, apart from the edits its
`PROVENANCE.md` or `CAPTURE.md` lists. The checks compare a service under test
against these files, so they are test fixtures, not code.

## Licences

- The captured data (HTTP exchanges, logs, metrics, database rows, Kafka
  dumps, trace exports) and the capture scripts are this repo's: MIT, see
  [`../LICENSE`](../LICENSE). Most of these formats can't carry an SPDX header.
- `*/asyncapi-html/` is the output of `@asyncapi/html-template` and contains
  its bundled CSS and JavaScript, which are AsyncAPI's under the Apache License
  2.0 (https://github.com/asyncapi/html-template). They are kept unmodified, as
  the service served them.
- The test data is made up: `example.com` addresses (RFC 2606), fixed or
  random UUIDs, and the published test passwords. See gluon's
  `docs/private-data-report.md`.
