# SPDX-License-Identifier: MIT

"""Fixtures for the integration tests: these start real local processes.

They need the PostgreSQL binaries (CONTRACT_PG_BIN, or pg_ctl on the PATH) and
nothing else: no Docker, no cluster, no network beyond 127.0.0.1.
"""

import os
from pathlib import Path

import pytest

from gluon_contract.config import find_pg_bin


@pytest.fixture(scope="session")
def pg_bin() -> Path:
    """The PostgreSQL binary directory, found the same way a run finds it."""
    return find_pg_bin(os.environ.get("CONTRACT_PG_BIN"))
