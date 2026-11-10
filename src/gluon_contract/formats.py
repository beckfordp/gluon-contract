# SPDX-License-Identifier: MIT

"""Formats the contract fixes (RUST-1.3, RUST-1.5).

Sources: capture 20261109 (`createdAt` as `Instant.toString` prints it,
token shapes) and ADR 0028 decision 5 (stored hash and token formats).
"""

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
"""32 random bytes, base64url without padding."""
PBKDF2_STORED = re.compile(
    r"^pbkdf2\$(?P<iterations>[1-9][0-9]*)\$(?P<salt>[A-Za-z0-9_-]{22})\$(?P<hash>[A-Za-z0-9_-]{43})$"
)
"""`pbkdf2$<iterations>$<16-byte salt>$<32-byte hash>`, base64url without padding."""
TRACEPARENT = re.compile(
    r"^00-(?P<trace>[0-9a-f]{32})-(?P<span>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$"
)


@dataclass(frozen=True, slots=True)
class TraceParent:
    """A W3C traceparent (version 00)."""

    trace_id: str
    span_id: str
    sampled: bool


def parse_traceparent(value: str) -> TraceParent | None:
    """The parts of a version-00 traceparent, or None if it isn't one."""
    match = TRACEPARENT.match(value)
    if match is None:
        return None
    return TraceParent(match["trace"], match["span"], bool(int(match["flags"], 16) & 1))


def java_instant(value: datetime) -> str:
    """How `java.time.Instant.toString` prints `value`: UTC, seconds always, and the
    fraction in 3 or 6 digits as needed (Postgres keeps microseconds).

    Raises:
        ValueError: for a naive datetime (no timezone, so no instant).
    """
    if value.tzinfo is None:
        raise ValueError("a naive datetime has no timezone, so it is not an instant")
    utc = value.astimezone(UTC)
    text = utc.strftime("%Y-%m-%dT%H:%M:%S")
    micros = utc.microsecond
    if micros % 1_000_000 == 0:
        return text + "Z"
    if micros % 1_000 == 0:
        return f"{text}.{micros // 1_000:03d}Z"
    return f"{text}.{micros:06d}Z"


def is_uuid(value: str) -> bool:
    """A lower-case hyphenated UUID, as the service renders ids."""
    return bool(UUID.match(value))


def is_token(value: str) -> bool:
    """An opaque token: 43 base64url characters, no padding."""
    return bool(TOKEN.match(value))


def _b64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def pbkdf2_matches(password: str, stored: str) -> bool:
    """Whether `stored` (the service's format) is PBKDF2-HMAC-SHA256 of the UTF-8 `password`."""
    match = PBKDF2_STORED.match(stored)
    if match is None:
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), _b64url(match["salt"]), int(match["iterations"]), 32
    )
    return hmac.compare_digest(derived, _b64url(match["hash"]))


def sha256_hex(text: str) -> str:
    """Lower-case hex SHA-256 of the UTF-8 text, as tokens are stored."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
