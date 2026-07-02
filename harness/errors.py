# SPDX-License-Identifier: Apache-2.0
"""The one exception the harness maps to a distinct exit code."""

from __future__ import annotations


class UsageError(Exception):
    """A usage/IO error — missing baseline, unreadable corpus, malformed
    queries, or a ``rac`` CLI that is absent or answers with an unexpected
    shape. The CLI maps this to exit code 2, distinct from a gate failure
    (exit 1) and a clean run (exit 0) — the same split ``rac eval`` uses.
    """
