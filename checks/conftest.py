# SPDX-License-Identifier: MIT

"""The contract checks: wired to the harness by gluon_contract.pytest_plugin.

Run by path, never by a bare `pytest` or CI (they start the build under test):
    uv run pytest checks --target-cmd "<command that starts the build>"
"""

from gluon_contract.pytest_plugin import (  # noqa: F401
    cdc,
    db,
    harness,
    harness_config,
    kafka,
    lookup_stub,
    probe,
    pytest_addoption,
    pytest_collection_modifyitems,
    pytest_configure,
    pytest_report_header,
    user_events,
)
