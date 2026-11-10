# SPDX-License-Identifier: MIT

"""REST contract of user-service (gluon PLAN.md RUST-1.3; ADR 0028, REST row).

Expectations come from the reference (ADR 0028 decision 2): the capture
`contracts/user-service/20261109` (`http/*.txt`, `openapi.yaml`), and ADR
0028's documented edge cases. Never from the implementation under test.
JSON bodies compare exactly as parsed JSON; framework text errors compare on
status, Content-Type and the exact prefix (decided 2026-11-09).
"""

import statistics
import time
import uuid
from typing import Any

import psycopg
import pytest

from gluon_contract.capture import load_exchange
from gluon_contract.formats import is_token, is_uuid, java_instant
from gluon_contract.harness import Harness
from gluon_contract.http import HttpResponse, json_body, request

pytestmark = pytest.mark.cluster
"""Runs in cluster mode too: these need only the service's API (RUST-5.4)."""


PASSWORD = "correct-horse-battery-1"
TEXT_PLAIN = "text/plain; charset=UTF-8"
JSON = {"Content-Type": "application/json"}


def new_email() -> str:
    """A throwaway address nobody else uses (product-guidelines.md)."""
    return f"contract-{uuid.uuid4().hex[:12]}@example.com"


def call(
    harness: Harness,
    method: str,
    path: str,
    payload: Any = None,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> HttpResponse:
    """One request to the service under test; `payload` is sent as JSON."""
    if payload is not None:
        body = json_body(payload)
        headers = JSON if headers is None else headers
    return request(harness.base_url, method, path, body=body, headers=headers)


def signup(harness: Harness, email: str, password: str = PASSWORD) -> HttpResponse:
    """POST /auth/signup."""
    return call(harness, "POST", "/auth/signup", {"email": email, "password": password})


def login(harness: Harness, email: str, password: str = PASSWORD) -> HttpResponse:
    """POST /auth/login."""
    return call(harness, "POST", "/auth/login", {"email": email, "password": password})


def assert_same(actual: HttpResponse, captured: str) -> None:
    """Status, Content-Type and JSON body exactly as in the capture."""
    expected = load_exchange(captured)
    assert (actual.status, actual.header("Content-Type")) == (
        expected.status,
        expected.header("Content-Type"),
    ), f"{captured}: body was {actual.text[:200]!r}"
    assert actual.json() == expected.json(), captured


def assert_text_error(
    actual: HttpResponse, status: int, text: str, *, prefix: bool = False
) -> None:
    """A framework error: plain text, exact or (for decode failures) exact up to the detail."""
    assert (actual.status, actual.header("Content-Type")) == (status, TEXT_PLAIN), actual.text[:200]
    if prefix:
        assert actual.text.startswith(text), actual.text
    else:
        assert actual.text == text


# --- POST /auth/signup -------------------------------------------------------


def test_signup_creates_an_account_and_returns_its_first_token(harness: Harness) -> None:
    """201 {userId, token}: a UUID and a 43-character base64url token.

    Source: capture http/signup-201.txt; ADR 0028 decision 5 (token format).
    """
    response = signup(harness, new_email())
    expected = load_exchange("signup-201")
    assert (response.status, response.header("Content-Type")) == (
        201,
        expected.header("Content-Type"),
    )
    body = response.json()
    assert set(body) == set(expected.json()) == {"userId", "token"}
    assert is_uuid(body["userId"]), body
    assert is_token(body["token"]), body


def test_signup_trims_and_lower_cases_the_email(harness: Harness) -> None:
    """The stored address is trimmed and lower-cased, Unicode included.

    Source: capture openapi.yaml ("trimmed and lower-cased before storage");
    CAPTURE.md's `  Capture.KAT@Example.com ` → http/users-200.txt.
    """
    local = uuid.uuid4().hex[:12]
    user_id = signup(harness, f"  ÄDA.{local}@Example.COM ").json()["userId"]
    assert call(harness, "GET", f"/users/{user_id}").json()["email"] == f"äda.{local}@example.com"


def test_signup_refuses_an_email_already_registered_after_normalisation(harness: Harness) -> None:
    """409 with the exact body, for the same address in another case.

    Source: capture http/signup-409.txt (same address, different case).
    """
    email = new_email()
    assert signup(harness, email).status == 201
    assert_same(signup(harness, email.upper()), "signup-409")


@pytest.mark.parametrize(
    "email", ["not-an-email", "no-domain@", "@no-local.com", "a b@example.com", ""]
)
def test_signup_refuses_an_invalid_email(harness: Harness, email: str) -> None:
    """400 {"error": "Enter a valid email address"}.

    Source: capture http/signup-400-email.txt.
    """
    assert_same(signup(harness, email), "signup-400-email")


def test_signup_refuses_a_password_under_8_characters(harness: Harness) -> None:
    """400 {"error": "Password must be at least 8 characters"}.

    Source: capture http/signup-400-short.txt.
    """
    assert_same(signup(harness, new_email(), "short"), "signup-400-short")


def test_password_length_is_counted_in_utf16_code_units(harness: Harness) -> None:
    """Four emoji are 8 UTF-16 units (accepted); seven é are 7 (refused).

    Source: ADR 0028 Context ("Signup counts password length in UTF-16 code units").
    """
    assert signup(harness, new_email(), "😀😀😀😀").status == 201
    assert_same(signup(harness, new_email(), "ééééééé"), "signup-400-short")


def test_only_ascii_whitespace_is_trimmed_from_an_email(harness: Harness) -> None:
    """A leading U+00A0 stays part of the address: a different account from the plain one.

    Source: ADR 0028 Context ("Email trimming only strips characters up to U+0020,
    and \\s in the email check is ASCII-only").
    """
    email = new_email()
    nbsp = signup(harness, "\u00a0" + email)
    assert nbsp.status == 201, nbsp.text
    assert signup(harness, email).status == 201
    assert (
        call(harness, "GET", f"/users/{nbsp.json()['userId']}").json()["email"] == "\u00a0" + email
    )


@pytest.mark.parametrize("content_type", ["text/plain", None])
def test_signup_does_not_check_the_content_type(harness: Harness, content_type: str | None) -> None:
    """A JSON body is read whatever the Content-Type says, or without one.

    Source: capture http/signup-text-plain.txt and http/signup-no-content-type.txt (both 201).
    """
    headers = {} if content_type is None else {"Content-Type": content_type}
    response = call(
        harness,
        "POST",
        "/auth/signup",
        body=json_body({"email": new_email(), "password": PASSWORD}),
        headers=headers,
    )
    assert response.status == 201, response.text


@pytest.mark.parametrize(
    ("body", "captured"),
    [
        (b"{not json", "signup-malformed-json"),
        (b'{"email":"a@example.com"}', "signup-missing-field"),
        (b'{"email":1,"password":true}', "signup-wrong-type"),
        (b"", "signup-empty-body"),
    ],
)
def test_an_undecodable_signup_body_is_a_plain_text_400(
    harness: Harness, body: bytes, captured: str
) -> None:
    """400 text/plain "Invalid value for: body (...)": the detail is the JSON library's own.

    Source: capture http/<captured>.txt; the user's 2026-11-09 decision on the prefix.
    """
    assert load_exchange(captured).text.startswith("Invalid value for: body (")
    response = call(harness, "POST", "/auth/signup", body=body, headers=JSON)
    assert_text_error(response, 400, "Invalid value for: body (", prefix=True)


def test_signup_with_the_wrong_method_is_405(harness: Harness) -> None:
    """GET on a POST route: 405 text/plain "Method Not Allowed".

    Source: capture http/signup-wrong-method.txt.
    """
    assert_text_error(
        call(harness, "GET", "/auth/signup"), 405, load_exchange("signup-wrong-method").text
    )


# --- POST /auth/login --------------------------------------------------------


def test_login_returns_the_account_and_a_fresh_token_pair(harness: Harness) -> None:
    """200 {userId, token, refreshToken}, for the same userId signup returned.

    Source: capture http/login-200.txt.
    """
    email = new_email()
    user_id = signup(harness, email).json()["userId"]
    response = login(harness, email)
    expected = load_exchange("login-200")
    assert (response.status, response.header("Content-Type")) == (
        200,
        expected.header("Content-Type"),
    )
    body = response.json()
    assert set(body) == set(expected.json()) == {"userId", "token", "refreshToken"}
    assert body["userId"] == user_id
    assert is_token(body["token"])
    assert is_token(body["refreshToken"])
    assert body["token"] != body["refreshToken"]


def test_login_normalises_the_email_as_signup_does(harness: Harness) -> None:
    """The address is trimmed and lower-cased before lookup.

    Source: capture openapi.yaml ("trimmed and lower-cased before lookup").
    """
    email = new_email()
    signup(harness, email)
    assert login(harness, f"  {email.upper()} ").status == 200


def test_a_wrong_password_and_an_unknown_email_get_the_same_401(harness: Harness) -> None:
    """One body for both, so the response doesn't reveal which emails are registered.

    Source: capture http/login-401-wrong-password.txt and http/login-401-unknown-email.txt.
    """
    email = new_email()
    signup(harness, email)
    assert_same(login(harness, email, "wrong-password-1"), "login-401-wrong-password")
    assert_same(login(harness, new_email(), "wrong-password-1"), "login-401-unknown-email")


def test_login_refuses_an_empty_password_and_an_invalid_email(harness: Harness) -> None:
    """400 "Enter your password" / "Enter a valid email address".

    Source: capture http/login-400-empty-password.txt; openapi.yaml (login 400: email invalid).
    """
    assert_same(login(harness, new_email(), ""), "login-400-empty-password")
    assert_same(login(harness, "not-an-email", PASSWORD), "signup-400-email")


def test_an_unknown_email_takes_as_long_as_a_wrong_password(harness: Harness) -> None:
    """Login hashes once even for an unknown email, so timing doesn't reveal registered emails.

    Source: capture openapi.yaml (login: "an unknown email still runs one password
    hash so timing doesn't reveal registered emails"). Medians of 3; unknown ≥ 50% of wrong.
    """
    email = new_email()
    signup(harness, email)

    def timed(address: str) -> float:
        started = time.perf_counter()
        assert login(harness, address, "wrong-password-1").status == 401
        return time.perf_counter() - started

    wrong = statistics.median(timed(email) for _ in range(3))
    unknown = statistics.median(timed(new_email()) for _ in range(3))
    assert unknown >= 0.5 * wrong, f"unknown email {unknown:.3f}s vs wrong password {wrong:.3f}s"


def test_an_undecodable_login_body_is_a_plain_text_400(harness: Harness) -> None:
    """As for signup.

    Source: capture http/login-malformed-json.txt.
    """
    response = call(harness, "POST", "/auth/login", body=b"{not json", headers=JSON)
    assert_text_error(response, 400, "Invalid value for: body (", prefix=True)


# --- GET /users/{id} ---------------------------------------------------------


@pytest.mark.isolated
def test_get_user_returns_id_email_and_creation_instant(
    harness: Harness, db: psycopg.Connection[tuple[Any, ...]]
) -> None:
    """200 {userId, email, createdAt}; createdAt is the stored instant as Java prints it.

    Source: capture http/users-200.txt (microsecond precision, `Z`).
    """
    email = new_email()
    user_id = signup(harness, email).json()["userId"]
    response = call(harness, "GET", f"/users/{user_id}")
    expected = load_exchange("users-200")
    assert (response.status, response.header("Content-Type")) == (
        200,
        expected.header("Content-Type"),
    )
    row = db.execute('select created_at from "user_account" where id = %s', (user_id,)).fetchone()
    assert row is not None
    assert response.json() == {"userId": user_id, "email": email, "createdAt": java_instant(row[0])}


def test_an_uppercase_id_is_answered_in_lower_case(harness: Harness) -> None:
    """The path id parses case-insensitively; the body renders it lower-case.

    Source: capture http/users-200-uppercase-id.txt.
    """
    user_id = signup(harness, new_email()).json()["userId"]
    response = call(harness, "GET", f"/users/{user_id.upper()}")
    assert response.status == 200
    assert response.json()["userId"] == user_id


def test_an_unknown_user_is_404(harness: Harness) -> None:
    """404 {"error": "User not found"}.

    Source: capture http/users-404.txt.
    """
    assert_same(call(harness, "GET", "/users/00000000-0000-0000-0000-000000000000"), "users-404")


def test_a_malformed_user_id_is_a_plain_text_400(harness: Harness) -> None:
    """400 text/plain "Invalid value for: path parameter id" (not in the OpenAPI spec).

    Source: capture http/users-400-malformed.txt.
    """
    response = call(harness, "GET", "/users/not-a-uuid")
    assert_text_error(response, 400, load_exchange("users-400-malformed").text)


@pytest.mark.parametrize(
    ("path_id", "status"),
    [
        ("1-2-3-4-5", 404),
        ("+1-+2-+3-+4-+5", 404),
        ("fffffffff-1-1-1-1", 404),
        ("0123456789abcdef0123456789abcdef", 400),
        ("%7B00000000-0000-0000-0000-000000000000%7D", 400),
        ("urn:uuid:00000000-0000-0000-0000-000000000000", 400),
        ("1--2-3-4", 400),
    ],
)
def test_a_user_id_parses_as_java_uuid_fromstring_does(
    harness: Harness, path_id: str, status: int
) -> None:
    """The id is whatever java.util.UUID.fromString accepts: five dash-separated
    hex groups of any length up to 36 characters in all (a group may carry a
    '+', and an overlong first group keeps its low 32 bits); no 32-digit
    undashed, braced or URN forms. Accepted ids that name nobody are 404.

    Source: tapir's UUID path codec (java.util.UUID.fromString), checked
    against the JDK; capture http/users-404.txt and users-400-malformed.txt for
    the two answers. Implicit behaviour (RUST-1.9).
    """
    response = call(harness, "GET", f"/users/{path_id}")
    if status == 404:
        assert_same(response, "users-404")
    else:
        assert_text_error(response, 400, load_exchange("users-400-malformed").text)


def test_a_user_with_the_wrong_method_is_405(harness: Harness) -> None:
    """DELETE on a GET route: 405 text/plain "Method Not Allowed".

    Source: capture http/users-wrong-method.txt.
    """
    response = call(harness, "DELETE", "/users/00000000-0000-0000-0000-000000000000")
    assert_text_error(response, 405, load_exchange("users-wrong-method").text)


# --- Anything else -------------------------------------------------------------


def test_an_unknown_path_is_a_plain_text_404(harness: Harness) -> None:
    """404 text/plain "Not found".

    Source: capture http/unknown-path.txt.
    """
    assert_text_error(
        call(harness, "GET", "/no-such-path"), 404, load_exchange("unknown-path").text
    )


CORS_HEADERS = (
    "Access-Control-Allow-Origin",
    "Access-Control-Allow-Methods",
    "Access-Control-Allow-Headers",
    "Access-Control-Expose-Headers",
    "Access-Control-Allow-Credentials",
    "Access-Control-Max-Age",
    "Vary",
)


def test_a_cors_preflight_is_answered_as_captured(harness: Harness) -> None:
    """200, empty; allow any origin, the five methods, Content-Type; no credentials.

    Source: capture http/cors-preflight.txt (header lists compared as sets).
    """
    response = call(
        harness,
        "OPTIONS",
        "/auth/signup",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    expected = load_exchange("cors-preflight")
    assert response.status == expected.status
    assert response.body == b""
    for name in CORS_HEADERS:
        assert response.header_set(name) == expected.header_set(name), name


def test_a_cross_origin_request_gets_the_cors_response_headers(harness: Harness) -> None:
    """Any origin allowed; X-Total-Count exposed; the response itself unchanged.

    Source: capture http/cors-simple.txt.
    """
    response = call(
        harness,
        "POST",
        "/auth/login",
        {"email": new_email(), "password": "wrong-password-1"},
        headers={"Origin": "http://localhost:5173", "Content-Type": "application/json"},
    )
    expected = load_exchange("cors-simple")
    assert response.status == expected.status
    for name in CORS_HEADERS:
        assert response.header_set(name) == expected.header_set(name), name


@pytest.mark.parametrize("path", ["/health", "/health/ready"])
def test_health_endpoints_answer_200_with_no_body(harness: Harness, path: str) -> None:
    """200, empty body, no Content-Type.

    Source: capture http/health.txt and http/health-ready.txt.
    """
    response = call(harness, "GET", path)
    assert (response.status, response.body, response.header("Content-Type")) == (200, b"", None)


@pytest.mark.isolated
def test_readiness_is_503_while_postgres_is_down(harness: Harness) -> None:
    """/health/ready answers 503 when Postgres doesn't answer a ping; /health stays 200.

    Source: capture openapi.yaml (readiness: "200 when Postgres answers a ping,
    503 when it doesn't"). Runs last: it stops and restarts the database.
    """
    harness.postgres.stop()
    try:
        assert call(harness, "GET", "/health/ready").status == 503
        assert call(harness, "GET", "/health").status == 200
    finally:
        harness.postgres.start()
    deadline = time.monotonic() + 30
    while call(harness, "GET", "/health/ready").status != 200:
        assert time.monotonic() < deadline, "not ready again 30 s after Postgres came back"
        time.sleep(0.2)
