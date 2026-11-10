# SPDX-License-Identifier: MIT

"""The scriptable lookup stub (RUST-6.1), exercised over real loopback HTTP."""

import http.client
import json
import socket
import time

import pytest

from gluon_contract.http_stub import Delay, HttpStub, Reset, Status

USER = "691b03e8-f1d7-45d9-a561-5183ffae9d0b"


def get(stub: HttpStub, path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    """One GET, (status, body)."""
    connection = http.client.HTTPConnection("127.0.0.1", stub.port, timeout=10)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_by_default_a_user_is_found_as_user_service_answers() -> None:
    """200 {userId, email, createdAt}, JSON."""
    with HttpStub() as stub:
        status, body = get(stub, f"/users/{USER}")
    assert status == 200
    assert json.loads(body) == {
        "userId": USER,
        "email": f"{USER}@example.com",
        "createdAt": "2026-11-09T18:43:19.511602Z",
    }


def test_scripted_answers_are_used_in_order_then_the_default() -> None:
    """Status(503), Status(404), then the default 200."""
    with HttpStub() as stub:
        stub.script(Status(503), Status(404))
        statuses = [get(stub, f"/users/{USER}")[0] for _ in range(3)]
    assert statuses == [503, 404, 200]


def test_a_delay_holds_the_answer_back() -> None:
    """Delay(0.5) answers after half a second (with the default unless told otherwise)."""
    with HttpStub() as stub:
        stub.script(Delay(0.5, Status(502)))
        started = time.monotonic()
        status, _ = get(stub, f"/users/{USER}")
        elapsed = time.monotonic() - started
    assert status == 502
    assert elapsed >= 0.5


def test_a_reset_closes_the_connection_without_an_answer() -> None:
    """The client sees the connection drop."""
    with HttpStub() as stub:
        stub.script(Reset())
        with pytest.raises((http.client.RemoteDisconnected, ConnectionResetError)):
            get(stub, f"/users/{USER}")
        assert get(stub, f"/users/{USER}")[0] == 200


def test_every_request_is_recorded_with_its_headers() -> None:
    """Method, path and headers (lower-case names), in arrival order."""
    with HttpStub() as stub:
        get(stub, f"/users/{USER}", {"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"})
        get(stub, "/other")
        requests = stub.requests()
        assert stub.wait_for_requests(2, timeout_s=1) == requests
    assert [(r.method, r.path) for r in requests] == [("GET", f"/users/{USER}"), ("GET", "/other")]
    assert requests[0].headers["traceparent"].startswith("00-111")


def test_waiting_for_requests_times_out_with_what_arrived() -> None:
    """An assertion error naming how many came."""
    with HttpStub() as stub, pytest.raises(AssertionError, match="0 of 1"):
        stub.wait_for_requests(1, timeout_s=0.2)


def test_the_port_is_free_after_stopping() -> None:
    """Nothing listens once the stub is closed."""
    with HttpStub() as stub:
        port = stub.port
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
