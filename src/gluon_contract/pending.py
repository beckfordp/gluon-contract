# SPDX-License-Identifier: MIT

"""PENDING: a check that has every piece of contract it needs and fails only because the
implementation under test hasn't built the feature yet (gluon RPN-10).

Such a check fails saying NOT_YET_IMPLEMENTED; anything else red is a FAIL (a
regression, or contract information missing). `check_report` classifies a failure
that says it as pending (`pend`), and `scripts/verify-check-group.sh --expect-red
"not yet implemented"` holds a group written before its feature to it. A check says
it only on evidence that the feature is absent (e.g. no consumer ever joined the
group), never merely because the check timed out.
"""

NOT_YET_IMPLEMENTED = "not yet implemented"
"""What a pending check's failure says; `verify-check-group.sh --expect-red` takes it."""
