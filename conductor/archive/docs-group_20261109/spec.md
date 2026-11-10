# Spec — RUST-1.4: Docs group

## Overview
gluon PLAN.md RUST-1.4 (ADR 0028 "Docs" row): the four docs paths are
served; the OpenAPI and AsyncAPI specs are equivalent to the Scala-generated
artifacts; every response conforms to the served OpenAPI spec. Sources:
capture 20261109 (`openapi.yaml`, `asyncapi.json`, `asyncapi-html/`,
`http/docs*.txt`, `http/asyncapi*.txt`), tapir `SwaggerUI` (1.11.x sources
from Maven Central: the yaml Content-Type, the redirect keeping the query),
purekafka `Docs.routes` (`/docs/asyncapi` → 301), swagger-ui webjar 5.20.7 (the
capture's `index.html` and initializer are byte-identical to it).

## Functional Requirements
1. `gluon_contract/openapi.py`: find the operation for a method and concrete
   path; say whether a response conforms (documented status, documented
   content type, JSON body valid against the schema with `$ref`s resolved).
2. `checks/test_docs.py`, each check with a `Source:` line:
   - `/docs` → 308 `./docs/` (query kept); `/docs/`, `/docs/index.html` the
     captured page; the initializer as captured; every asset the page loads
     served;
   - `/docs/docs.yaml`: `application/yaml; charset=UTF-8`, parsed equal to the
     captured `openapi.yaml`;
   - responses to the REST scenarios conform to the served spec, except
     exactly the ones the Scala service also gets wrong (undocumented
     statuses and plain-text decode failures, from the capture);
   - `/docs/asyncapi.json` parsed equal to the captured one; `/docs/asyncapi`
     → 301 `/docs/asyncapi/`; the HTML page, CSS and JS byte-equal to the
     captured `asyncapi-html/` (html-template 3.5.6 renders deterministically).

## Acceptance Criteria
- `scripts/verify-docs-group.sh` PASS: CI green, every check names its source;
  the group runs against the Rust build (red until RUST-4.1/4.2).
