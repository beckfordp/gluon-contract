# SPDX-License-Identifier: MIT

"""Docs (gluon PLAN.md RUST-1.4; ADR 0028 "Docs" row).

Reference: capture 20261109 (openapi.yaml, asyncapi.json, asyncapi-html/,
http/docs*.txt, http/asyncapi*.txt), tapir SwaggerUI (1.11.x sources: the
redirect keeping the query), purekafka Docs.routes (/docs/asyncapi → 301), the
swagger-ui 5.20.7 webjar the capture's page and initializer are byte-identical
to, the RUST-5.0 run against the Scala service (the yaml endpoint's
Content-Type, which the capture lacks).
"""

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import JSON, new_email, signed_up

from gluon_contract.capture import capture_file, load_exchange
from gluon_contract.harness import Harness
from gluon_contract.http import HttpResponse, request
from gluon_contract.openapi import conformance, load_spec

pytestmark = [pytest.mark.service("user-service"), pytest.mark.cluster]
"""user-service's contract (deselected in a run for another service, RPN-3); runs in
cluster mode too: these need only the service's API (RUST-5.4)."""


CREDENTIALS = b'{"email":"%s","password":"correct-horse-battery-1"}'


def get(harness: Harness, path: str) -> HttpResponse:
    """GET `path` from the service under test."""
    return request(harness.base_url, "GET", path)


# --- Swagger UI and the OpenAPI spec ------------------------------------------


def test_docs_redirects_to_the_swagger_ui(harness: Harness) -> None:
    """GET /docs: 308 to the relative ./docs/, no body.

    Source: capture http/docs.txt.
    """
    response = get(harness, "/docs")
    expected = load_exchange("docs")
    assert (response.status, response.header("Location"), response.body) == (
        expected.status,
        expected.header("Location"),
        b"",
    )


def test_the_redirect_keeps_the_query(harness: Harness) -> None:
    """GET /docs?… redirects to ./docs/?… (Swagger UI reads its options from the query).

    Source: tapir SwaggerUI redirectToSlashEndpoint (query params appended).
    Implicit behaviour (RUST-1.9).
    """
    response = get(harness, "/docs?urls.primaryName=user")
    assert (response.status, response.header("Location")) == (308, "./docs/?urls.primaryName=user")


@pytest.mark.parametrize(
    ("path", "captured"), [("/docs/", "docs-slash"), ("/docs/index.html", "docs-index")]
)
def test_the_swagger_ui_page_is_served(harness: Harness, path: str, captured: str) -> None:
    """The swagger-ui page, as captured (text/html).

    Source: capture http/docs-slash.txt, http/docs-index.txt (swagger-ui 5.20.7's index.html).
    """
    response = get(harness, path)
    expected = load_exchange(captured)
    assert (response.status, response.header("Content-Type")) == (
        200,
        expected.header("Content-Type"),
    )
    assert response.body == expected.body


def test_the_initializer_loads_docs_yaml(harness: Harness) -> None:
    """swagger-initializer.js as captured: url "./docs.yaml", showExtensions false.

    Source: capture http/docs-initializer.txt.
    """
    response = get(harness, "/docs/swagger-initializer.js")
    expected = load_exchange("docs-initializer")
    assert (response.status, response.header("Content-Type")) == (
        200,
        expected.header("Content-Type"),
    )
    assert response.body == expected.body


def test_every_asset_the_page_loads_is_served(harness: Harness) -> None:
    """Each stylesheet, script and icon index.html references answers 200 with content.

    Source: capture http/docs-index.txt (the references); tapir SwaggerUI (the
    webjar's files served under /docs/).
    """
    page = load_exchange("docs-index").text
    assets = sorted({ref.removeprefix("./") for ref in re.findall(r'(?:href|src)="([^"]+)"', page)})
    assert "swagger-ui-bundle.js" in assets
    missing = {
        asset: response.status
        for asset in assets
        if (response := get(harness, f"/docs/{asset}")).status != 200 or not response.body
    }
    assert missing == {}


def test_the_openapi_spec_is_the_scala_one(harness: Harness) -> None:
    """GET /docs/docs.yaml: application/yaml (no charset), parsed equal to the captured spec.

    Source: capture openapi.yaml; the Content-Type from the RUST-5.0 run against the Scala
    service (2026-11-10), as the capture has no GET headers (PROVENANCE.md).
    """
    response = get(harness, "/docs/docs.yaml")
    assert (response.status, response.header("Content-Type")) == (200, "application/yaml")
    assert yaml.safe_load(response.text) == yaml.safe_load(capture_file("openapi.yaml").read_text())


# The REST exchanges the capture made (CAPTURE.md), re-made here: name →
# (method, path, headers, body). USER is replaced by a fresh account's id.
SCENARIOS: dict[str, tuple[str, str, dict[str, str] | None, bytes | None]] = {
    "signup-201": ("POST", "/auth/signup", JSON, CREDENTIALS % b"NEW"),
    "signup-409": ("POST", "/auth/signup", JSON, CREDENTIALS % b"EXISTING"),
    "signup-400-email": ("POST", "/auth/signup", JSON, CREDENTIALS % b"not-an-email"),
    "signup-400-short": (
        "POST",
        "/auth/signup",
        JSON,
        b'{"email":"short@example.com","password":"short"}',
    ),
    "signup-malformed-json": ("POST", "/auth/signup", JSON, b"{not json"),
    "signup-missing-field": ("POST", "/auth/signup", JSON, b'{"email":"a@example.com"}'),
    "signup-wrong-type": ("POST", "/auth/signup", JSON, b'{"email":1,"password":true}'),
    "signup-empty-body": ("POST", "/auth/signup", JSON, None),
    "signup-text-plain": (
        "POST",
        "/auth/signup",
        {"Content-Type": "text/plain"},
        CREDENTIALS % b"NEW",
    ),
    "signup-wrong-method": ("GET", "/auth/signup", None, None),
    "login-200": ("POST", "/auth/login", JSON, CREDENTIALS % b"EXISTING"),
    "login-401-wrong-password": (
        "POST",
        "/auth/login",
        JSON,
        b'{"email":"EXISTING","password":"wrong-password-1"}',
    ),
    "login-401-unknown-email": (
        "POST",
        "/auth/login",
        JSON,
        b'{"email":"nobody@example.com","password":"wrong-password-1"}',
    ),
    "login-400-empty-password": (
        "POST",
        "/auth/login",
        JSON,
        b'{"email":"EXISTING","password":""}',
    ),
    "login-malformed-json": ("POST", "/auth/login", JSON, b"{not json"),
    "users-200": ("GET", "/users/USER", None, None),
    "users-404": ("GET", "/users/00000000-0000-0000-0000-000000000000", None, None),
    "users-400-malformed": ("GET", "/users/not-a-uuid", None, None),
    "users-wrong-method": ("DELETE", "/users/USER", None, None),
    "unknown-path": ("GET", "/no-such-path", None, None),
    "health": ("GET", "/health", None, None),
    "health-ready": ("GET", "/health/ready", None, None),
}


def captured_conformance(spec: dict[str, Any], name: str) -> str | None:
    """How the Scala service's captured response measured up to its own spec."""
    method, path, _, _ = SCENARIOS[name]
    concrete = path.replace("USER", "691b03e8-f1d7-45d9-a561-5183ffae9d0b")
    return conformance(spec, method, concrete, load_exchange(name))


def test_responses_conform_to_the_served_spec_as_the_scala_ones_do(harness: Harness) -> None:
    """Each REST scenario's response conforms to the served spec exactly when the captured
    Scala response conforms to the captured spec. The Scala service's own gaps (decode
    failures answered in text/plain, 400 for a malformed id, 405s, the unknown-path 404)
    stay gaps; everything else must conform.

    Source: capture openapi.yaml and http/*.txt (ADR 0028 names the malformed-id 400 as
    a status the spec doesn't list).
    """
    served = load_spec(get(harness, "/docs/docs.yaml").text)
    captured_spec = load_spec(capture_file("openapi.yaml").read_text())
    email = new_email()
    user_id = signed_up(harness, email)["userId"]
    outcomes: dict[str, tuple[bool, bool, str | None]] = {}
    for name, (method, path, headers, body) in SCENARIOS.items():
        fresh = f"contract-{uuid.uuid4().hex[:12]}@example.com"
        payload = (
            None
            if body is None
            else body.replace(b"NEW", fresh.encode()).replace(b"EXISTING", email.encode())
        )
        concrete = path.replace("USER", user_id)
        reason = conformance(
            served,
            method,
            concrete,
            request(harness.base_url, method, concrete, body=payload, headers=headers),
        )
        expected = captured_conformance(captured_spec, name)
        outcomes[name] = (reason is None, expected is None, reason)
    mismatched = {name: o for name, o in outcomes.items() if o[0] != o[1]}
    assert mismatched == {}, mismatched
    gaps = sorted(name for name, o in outcomes.items() if not o[1])
    assert gaps == [
        "login-malformed-json",
        "signup-empty-body",
        "signup-malformed-json",
        "signup-missing-field",
        "signup-wrong-method",
        "signup-wrong-type",
        "unknown-path",
        "users-400-malformed",
        "users-wrong-method",
    ]


@pytest.mark.parametrize("path", ["/docs/docs.yaml", "/docs/", "/health", "/users/USER"])
def test_head_on_a_get_path_is_405(harness: Harness, path: str) -> None:
    """HEAD is not GET: tapir answers 405 text/plain "Method Not Allowed".

    Source: capture http/docs-yaml-headers.txt (HEAD /docs/docs.yaml); tapir's
    method matching, the same for every GET endpoint. Implicit behaviour (RUST-1.9).
    """
    concrete = path.replace("USER", "00000000-0000-0000-0000-000000000000")
    response = request(harness.base_url, "HEAD", concrete)
    expected = load_exchange("docs-yaml-headers")
    assert (response.status, response.header("Content-Type")) == (
        expected.status,
        expected.header("Content-Type"),
    )


def test_an_unknown_file_under_docs_is_an_empty_404(harness: Harness) -> None:
    """Swagger UI's resource endpoint owns /docs/*: an unknown file is its 404, with no body
    (not the plain-text "Not found" of an unknown path).

    Source: tapir-files (StaticErrorOutput.NotFound → 404, empty); user-service
    AppRoutes (the Swagger bundle "returns its own real 404" for /docs/*). Implicit
    behaviour (RUST-1.9).
    """
    for path in ["/docs/no-such-file.js", "/docs/asyncapi/no-such-file.js"]:
        response = get(harness, path)
        assert (response.status, response.body) == (404, b""), path


# --- AsyncAPI -------------------------------------------------------------------


def test_the_asyncapi_spec_is_the_scala_one(harness: Harness) -> None:
    """GET /docs/asyncapi.json: application/json, parsed equal to the captured spec.

    Source: capture asyncapi.json and http/asyncapi-json.txt.
    """
    response = get(harness, "/docs/asyncapi.json")
    expected = load_exchange("asyncapi-json")
    assert (response.status, response.header("Content-Type")) == (
        200,
        expected.header("Content-Type"),
    )
    assert response.json() == json.loads(capture_file("asyncapi.json").read_text())


def test_asyncapi_without_the_slash_redirects(harness: Harness) -> None:
    """GET /docs/asyncapi: 301 to /docs/asyncapi/ (the page's css/ and js/ are relative).

    Source: purekafka Docs.routes (MovedPermanently(Location(/docs/asyncapi/))).
    """
    response = get(harness, "/docs/asyncapi")
    assert (response.status, response.header("Location")) == (301, "/docs/asyncapi/")


HTML_FILES = [
    "index.html",
    "css/asyncapi.min.css",
    "css/global.min.css",
    "js/app.js",
    "js/asyncapi-ui.min.js",
]


@pytest.mark.parametrize("path", ["/docs/asyncapi/", "/docs/asyncapi/index.html"])
def test_the_asyncapi_page_is_served(harness: Harness, path: str) -> None:
    """The rendered AsyncAPI page, text/html, byte-equal to the Scala build's.

    Source: capture http/asyncapi-slash.txt, asyncapi-index.txt, asyncapi-html/index.html
    (html-template 3.5.6 renders the same spec to the same bytes).
    """
    response = get(harness, path)
    assert (response.status, response.header("Content-Type")) == (200, "text/html")
    assert response.body == capture_file("asyncapi-html/index.html").read_bytes()


@pytest.mark.parametrize("name", HTML_FILES[1:])
def test_the_asyncapi_page_assets_are_the_scala_ones(harness: Harness, name: str) -> None:
    """Each CSS and JS file the page loads, byte-equal to the Scala build's.

    Source: capture asyncapi-html/ (css/, js/).
    """
    response = get(harness, f"/docs/asyncapi/{name}")
    assert response.status == 200
    assert response.body == capture_file(f"asyncapi-html/{name}").read_bytes()


def test_the_captured_asyncapi_html_is_complete() -> None:
    """The capture holds every file the page loads (guards the checks above).

    Source: capture asyncapi-html/index.html (its css/ and js/ references).
    """
    page = capture_file("asyncapi-html/index.html").read_text()
    referenced = set(re.findall(r'(?:href|src)="((?:css|js)/[^"]+)"', page))
    assert referenced == set(HTML_FILES[1:])
    assert all(Path(capture_file(f"asyncapi-html/{name}")).is_file() for name in HTML_FILES)
