# Implicit behaviours of user-service (gluon PLAN.md RUST-1.9)

Behaviour of the Scala user-service (and of purerest/purekafka under it) that
no document stated, found while porting it to Rust (ADR 0028 decision 3).
Each is now a check naming its source, first seen failing against a build
without it, then green against the Rust service. "Gap" says whether it is a
documentation gap and where it is raised: **gluon** gaps are written into
`docs/system-design.md` in the same change as this list; **user-service**
gaps are OpenAPI descriptions in the Scala repo, raised for the laptop pass
(Rust Spike 5), since the Scala build can't run in the sandbox.

The list is checked by `scripts/verify-implicit-behaviours.sh`: every check
named here exists, and (with `--run`) passes against the Rust build.

| # | Behaviour | Source | Check | Gap, where raised |
|---|---|---|---|---|
| 1 | Password length counts UTF-16 code units (`😀😀😀😀` is 8) | ADR 0028 (found reviewing it); Scala `Password` | `test_rest.py::test_password_length_is_counted_in_utf16_code_units` | user-service OpenAPI: "at least 8 characters" doesn't say which |
| 2 | Email trimming strips only characters up to U+0020; the email pattern's `\s` is ASCII-only | ADR 0028; Scala `Email` | `test_rest.py::test_only_ascii_whitespace_is_trimmed_from_an_email` | user-service OpenAPI ("trimmed") |
| 3 | A malformed `/users/{id}` is a plain-text 400 the spec doesn't list | capture `users-400-malformed.txt` | `test_rest.py::test_a_malformed_user_id_is_a_plain_text_400`, `test_docs.py::test_responses_conform_to_the_served_spec_as_the_scala_ones_do` | user-service OpenAPI (no 400 on `getUsersId`); gluon system-design already lists it |
| 4 | Ids parse as `java.util.UUID.fromString`: `1-2-3-4-5` is an id (404), 32 undashed digits aren't (400) | tapir's UUID codec; the JDK (658 known-answer vectors) | `test_rest.py::test_a_user_id_parses_as_java_uuid_fromstring_does` | **gluon**: system-design `GET /users/{id}` (done); user-service OpenAPI |
| 5 | `http_route` collapses a segment to `{id}` exactly when `UUID.fromString` accepts it | purerest `ServerMetrics.routeTemplate` | `test_metrics.py::test_a_segment_is_an_id_when_java_would_parse_it_as_a_uuid` | no (ADR 0028 names the raw-path route) |
| 6 | Signup and login decode JSON whatever the Content-Type (text/plain, none) | capture `signup-text-plain.txt`, `signup-no-content-type.txt` | `test_rest.py::test_signup_does_not_check_the_content_type` | user-service OpenAPI (lists only application/json) |
| 7 | Undecodable bodies are 400 `text/plain` `Invalid value for: body (…)`, not the documented JSON error | capture `signup-malformed-json.txt` and siblings | `test_rest.py::test_an_undecodable_signup_body_is_a_plain_text_400`, `test_docs.py::test_responses_conform_to_the_served_spec_as_the_scala_ones_do` | user-service OpenAPI |
| 8 | Error variants sharing a status merge: the spec's 400 says only "Email is invalid." (and its example), though a short password is also 400 | capture `openapi.yaml`; tapir | `test_docs.py::test_the_openapi_spec_is_the_scala_one` | user-service OpenAPI (tapir's merge; worth a combined description) |
| 9 | HEAD on any GET path is 405 | capture `docs-yaml-headers.txt` | `test_docs.py::test_head_on_a_get_path_is_405` | no |
| 10 | An unknown file under `/docs/` is an empty 404 (Swagger UI's resources endpoint), unlike the text "Not found" elsewhere | tapir-files; `AppRoutes` | `test_docs.py::test_an_unknown_file_under_docs_is_an_empty_404` | no |
| 11 | `/docs?…` redirects to `./docs/?…`, keeping the query | tapir `SwaggerUI` | `test_docs.py::test_the_redirect_keeps_the_query` | no |
| 12 | The AsyncAPI payload schema is JSON Schema 2020-12 and open; the registry's is draft-07 and closed | capture `asyncapi.json`; `registry/user-service/registry.json` | `test_docs.py::test_the_asyncapi_spec_is_the_scala_one`; user-service-rs `tests/events.rs` | **gluon**: system-design "Kafka topics" (done) |
| 13 | Debezium's router adds an `id` header (the outbox row id) besides `traceparent` and `correlation_id` | the sandbox CDC stack (Debezium 3.0.0, gluon's connector config) | `test_cdc.py::test_a_signup_is_published_on_user_events_as_registered`, `test_cdc.py::test_the_outbox_groups_stand_in_routes_as_debezium_does` | **gluon**: system-design "Envelope", Kafka headers (done) |
| 14 | A NULL outbox field still becomes a header, with no value | the sandbox CDC stack; purekafka `KafkaTracing.extractCarrier` | unit `tests/unit/test_routing_registry.py::test_a_null_field_gives_a_header_with_no_value` (the Rust service always writes `trace_parent`) | **gluon**: system-design "Envelope" (done) |
| 15 | The envelope's `source` is always `user-service`, whatever `USER_SERVICE_NAME` says | Scala `AuthEvents` (a constant) | `test_config.py::test_the_event_source_stays_user_service` | no (system-design says "the publishing service's name") |
| 16 | A path no route matches is traced and metered without `http.response.status_code` | capture `stdout.log`, `metrics.txt`; purerest `ServerTracing`, `ServerMetrics` | `test_traces.py::test_an_unmatched_path_span_has_no_status_code`, `test_metrics.py::test_an_unmatched_path_is_recorded_without_a_status_code` | no |
| 17 | CORS answers a preflight outside tracing and metrics: no span, no series | capture (no OPTIONS span or series); `AppRoutes` | `test_traces.py::test_a_cors_preflight_is_not_traced`, `test_metrics.py::test_a_cors_preflight_is_not_recorded` | no |
| 18 | Only a 5xx marks a server span ERROR | purerest `ServerTracing` | `test_traces.py::test_only_a_server_error_marks_the_span_as_error` | no |
| 19 | `otel_scope_name` and `logger_name` are `USER_SERVICE_NAME` | purerest `Metrics.oteljava`, `Logging.create` | `test_config.py::test_the_service_name_scopes_the_metrics`, `test_config.py::test_the_service_name_names_the_logger` | no |
| 20 | Each outcome logs its own message, level and fields, in the request's trace (what Kibana searches rely on) | capture `stdout.log`; `AuthRoutes`, `UserRoutes` | `test_logs.py::test_each_outcome_logs_its_message_at_its_level` | no |
| 21 | User log lines carry the canonical (lower-case) id in `path` and `user_id`, whatever the request's case | capture `stdout.log`; `UserRoutes` | `test_logs.py::test_a_user_path_is_logged_with_the_canonical_id` | no |
| 22 | Requests that fail to decode log nothing | capture `stdout.log` (7 lines for 11 signup spans) | `test_logs.py::test_a_request_that_fails_to_decode_logs_nothing` | no |
| 23 | `@timestamp` is UTC with the fraction's trailing zeros dropped (`20.75179Z`) | capture; logstash-logback-encoder | `test_logs.py::test_timestamps_are_utc_with_the_fraction_trimmed` | no |
| 24 | purerest's HTTP retry skips a connection reset mid-response; only the DLQ guard's processing retry tries again | purerest `Retry.isRetriableError` | `test_probe.py::test_transient_failures_are_retried` | **gluon**: system-design "Consume-time lookups" (done) |
| 25 | An exhausted 5xx comes back as the response, so the two retry layers multiply | purerest `Retry`; notification-service `UserClient` | `test_probe.py::test_persistent_failures_are_dead_lettered_after_both_retry_layers` | **gluon**: system-design "Consume-time lookups" (done) |

## Not checked, and why

| Behaviour | Why there is no check |
|---|---|
| `traceparent`'s flags are `03` (W3C random-trace-id flag) in Scala, `01` in Rust | Not contract: only the sampled bit is (decided 2026-11-09) |
| `error.type` values are Java exception class names | A Rust service can't reproduce them; the label is checked by name only |
| `jvm_*`, `cats_effect_*` and `target_info` families | Runtime-specific; ADR 0028 expects the JVM panels to be empty for Rust |
| Flyway's and http4s's own log lines | Other loggers; not what Filebeat's consumers search |
| Envelope `timestamp` resolution (microseconds, Java's clock) | Reproduced, but the contract is "ISO-8601 instant" |
| The body and log line of a 500 when Postgres fails mid-request | Not captured: needs a laptop capture (RUST-5.0) before it can be a check |
| Swagger UI's source maps and ES bundles (served by the webjar) | No page loads them; the Rust service serves the files the page needs |
