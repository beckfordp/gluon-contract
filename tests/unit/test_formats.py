# SPDX-License-Identifier: MIT

"""Formats the contract fixes (RUST-1.3 helpers)."""

import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest

from gluon_contract.formats import (
    PBKDF2_STORED,
    is_token,
    is_uuid,
    java_instant,
    pbkdf2_matches,
    sha256_hex,
)

SCALA_HASH = "pbkdf2$210000$I0d_rX5N6NLp3Allk1Z5ew$NRZ6suRMJFGRTlEcj32skfkNperlROT1Wj5rvBiEHBY"


@pytest.mark.parametrize(
    ("value", "printed"),
    [
        (datetime(2026, 11, 9, 18, 43, 19, 511602, tzinfo=UTC), "2026-11-09T18:43:19.511602Z"),
        (datetime(2026, 11, 9, 18, 43, 19, 511000, tzinfo=UTC), "2026-11-09T18:43:19.511Z"),
        (datetime(2026, 11, 9, 18, 43, 19, 500, tzinfo=UTC), "2026-11-09T18:43:19.000500Z"),
        (datetime(2026, 11, 9, 18, 43, 0, tzinfo=UTC), "2026-11-09T18:43:00Z"),
        (
            datetime(2026, 11, 9, 19, 43, 19, 511602, tzinfo=timezone(timedelta(hours=1))),
            "2026-11-09T18:43:19.511602Z",
        ),
    ],
)
def test_instants_print_as_java_does(value: datetime, printed: str) -> None:
    """java.time.Instant.toString: UTC, seconds always, fraction in groups of 3 digits."""
    assert java_instant(value) == printed


def test_a_naive_datetime_is_refused() -> None:
    """Without a zone there is no instant."""
    with pytest.raises(ValueError, match="timezone"):
        java_instant(datetime(2026, 11, 9))


def test_token_and_uuid_shapes() -> None:
    """Tokens are 32 random bytes, base64url without padding: 43 characters."""
    assert is_token("EXAMPLE-access-token-signup-201-not-real-00")
    assert not is_token("too-short")
    assert not is_token("EXAMPLE-access-token-signup-201-not-real-00=")
    assert is_uuid("691b03e8-f1d7-45d9-a561-5183ffae9d0b")
    assert not is_uuid("691B03E8-F1D7-45D9-A561-5183FFAE9D0B")
    assert not is_uuid("not-a-uuid")


def test_the_scala_services_stored_hash_verifies() -> None:
    """A known-answer vector from the capture (db-user-account.txt, CAPTURE.md's password)."""
    assert PBKDF2_STORED.match(SCALA_HASH)
    assert pbkdf2_matches("correct-horse-battery-1", SCALA_HASH)
    assert not pbkdf2_matches("wrong-password-1", SCALA_HASH)
    assert not pbkdf2_matches("anything", "bcrypt$10$abc")


def test_sha256_hex() -> None:
    """Tokens are stored as the lower-case hex SHA-256 of their text."""
    assert sha256_hex("abc") == hashlib.sha256(b"abc").hexdigest()
