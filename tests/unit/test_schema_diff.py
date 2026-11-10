# SPDX-License-Identifier: MIT

"""Comparing schema snapshots (RUST-1.5 helper)."""

from gluon_contract.schema import Snapshot, diff_snapshots

BASE: Snapshot = {
    "columns": {("user_account", "email"): ("text", "NO", None)},
    "constraints": {("user_account", "user_account_email_key"): ("u", "UNIQUE (email)")},
    "indexes": {"user_account_email_key": "CREATE UNIQUE INDEX ... (email)"},
    "tables": {"user_account"},
}


def test_identical_snapshots_have_no_differences() -> None:
    """Nothing to report."""
    assert diff_snapshots(BASE, BASE) == []


def test_every_kind_of_difference_is_listed() -> None:
    """Missing, extra and changed items, each named."""
    other: Snapshot = {
        "columns": {("user_account", "email"): ("character varying", "NO", None)},
        "constraints": {},
        "indexes": {
            "user_account_email_key": "CREATE UNIQUE INDEX ... (email)",
            "extra_idx": "...",
        },
        "tables": {"user_account", "extra_table"},
    }
    differences = diff_snapshots(BASE, other)
    assert any("column user_account.email" in d and "character varying" in d for d in differences)
    assert any(
        "constraint user_account.user_account_email_key" in d and "missing" in d
        for d in differences
    )
    assert any("index extra_idx" in d and "unexpected" in d for d in differences)
    assert any("table extra_table" in d and "unexpected" in d for d in differences)
    assert len(differences) == 4
