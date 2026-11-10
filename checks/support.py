# SPDX-License-Identifier: MIT

"""Shared by the check modules: requests to the service and throwaway data."""

import secrets
import uuid
from typing import Any

from gluon_contract.harness import Harness
from gluon_contract.http import HttpResponse, json_body, request

PASSWORD = "correct-horse-battery-1"
JSON = {"Content-Type": "application/json"}


def new_email() -> str:
    """A throwaway address nobody else uses (product-guidelines.md)."""
    return f"contract-{uuid.uuid4().hex[:12]}@example.com"


def new_traceparent() -> str:
    """A fresh, sampled W3C traceparent, so a check's spans are its own."""
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def base_url_of(target: Harness | str) -> str:
    """The base URL of the harness's instance, or `target` itself when it is one."""
    return target if isinstance(target, str) else target.base_url


def post_credentials(
    target: Harness | str,
    path: str,
    email: str,
    password: str = PASSWORD,
    *,
    traceparent: str | None = None,
) -> HttpResponse:
    """POST a credentials body, optionally carrying a traceparent.

    `target` is the harness (its instance) or another instance's base URL.
    """
    headers = dict(JSON)
    if traceparent is not None:
        headers["traceparent"] = traceparent
    body = json_body({"email": email, "password": password})
    return request(base_url_of(target), "POST", path, body=body, headers=headers)


def signed_up(target: Harness | str, email: str, **kwargs: Any) -> dict[str, Any]:
    """Signs up and returns the 201 body."""
    response = post_credentials(target, "/auth/signup", email, **kwargs)
    assert response.status == 201, f"signup: {response.status} {response.text[:200]}"
    body: dict[str, Any] = response.json()
    return body
