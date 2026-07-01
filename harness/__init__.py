# SPDX-License-Identifier: Apache-2.0
"""Shared harness for the per-tool RAC benchmark suite.

One benchmark subdir per Lore MCP tool (ADR-092 family form); each subdir is a
thin entry point over this package. The harness drives ``rac`` strictly as an
external CLI on ``PATH`` (DG-ADR-0001 — zero engine imports), parses its
``--json`` output, scores it deterministically (ADR-066 — no embeddings, no
LLM judge, no network, no randomness, no clock in the scored path), and writes
a ``{metrics, metadata, per_query}`` scorecard whose serialized ``metrics``
block is byte-identical across runs on an unchanged corpus.

Flag surface mirrors ``rac eval`` exactly: ``--check | --update-baseline``,
``--json``, ``--root``, ``--queries``, ``--baseline``, ``--config``. Exit
codes: 0 clean, 1 gate failure, 2 usage error. The scorecard JSON is a stable,
additive contract (ADR-007). Re-baselining is human-gated; CI never passes
``--update-baseline``.
"""

from harness.cli import main

__all__ = ["main"]
