# SPDX-License-Identifier: Apache-2.0
"""Grounding arms for the GitChameleon evidence run.

Arms differ ONLY in how they assemble grounding context for the held-constant
answering model (the DG-ADR-0001 single-variable design):

- ``no_grounding`` — the problem alone; the model answers from its weights.
- ``rac``          — the governing version-pin decision retrieved from the
  example's corpus via the live-decision query (`rac find --decisions`),
  driven strictly as an external CLI through the shared harness runner.
- ``naive_rag``    — embedding retrieval over the same corpus. Deliberately a
  seam: the embedder is pinned at funded-run time (mirroring
  decisiongrounding's embedder choice), so the scaffold refuses rather than
  silently shipping a weak stand-in.
"""

from __future__ import annotations

from pathlib import Path

from harness.runner import RacRunner

ARMS = ("no_grounding", "rac", "naive_rag")
# How many retrieved decisions the rac arm feeds the answering model.
RAC_TOP_K = 3


def rac_grounding(runner: RacRunner, corpus_dir: Path, row: dict) -> list[str]:
    """The rac arm: live-decision retrieval, retrieved artifacts verbatim.

    The query is what an agent grounding itself would ask before writing code
    against a library: which live decisions bind this dependency?
    """
    query = f"{row['library']} version pin"
    returned = runner.find_ids(query, str(corpus_dir), decisions=True)
    grounding: list[str] = []
    for artifact_id in returned[:RAC_TOP_K]:
        resolved = runner.resolve(artifact_id, str(corpus_dir))
        payload = resolved.payload()
        if resolved.exit_code == 0 and "path" in payload:
            grounding.append(Path(payload["path"]).read_text(encoding="utf-8"))
    return grounding


def assemble_grounding(
    arm: str, runner: RacRunner | None, corpus_dir: Path, row: dict
) -> list[str]:
    """The grounding context one arm supplies for one example."""
    if arm == "no_grounding":
        return []
    if arm == "rac":
        if runner is None:
            raise ValueError("the rac arm needs a RacRunner (rac CLI on PATH)")
        return rac_grounding(runner, corpus_dir, row)
    if arm == "naive_rag":
        raise NotImplementedError(
            "naive_rag is a funded-run seam: pin the embedder there "
            "(decisiongrounding pins voyage:voyage-4-large as the strong "
            "published baseline) rather than shipping a weak lexical stand-in"
        )
    raise ValueError(f"unknown arm {arm!r}; expected one of {ARMS}")


def task_prompt(row: dict) -> str:
    """The held-constant task prompt every arm shares (grounding excluded).

    Deliberately does NOT restate the pinned version: version awareness must
    come from the arm's grounding (or the model's weights), or the comparison
    measures prompt engineering instead of grounding. The upstream problem
    statement itself is preserved verbatim.
    """
    return (
        "Complete the following Python function for this codebase.\n\n"
        f"Problem: {row['problem']}\n\n"
        "Starting code:\n"
        "```python\n"
        f"{row['starting_code']}\n"
        "```\n\n"
        "Return only the completed code."
    )
