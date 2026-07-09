"""Measure the lexical overlap between a scenario's task vocabulary and the
real PEP distractor domain.

The benchmark's sharpest failure mode is lexical: when the task's words are
topically dense in the distractor titles (every PEP title is Python-topical),
an embedding retriever ranks distractors above the buried binding decision. In
the pilot, one scenario (prohibition_language_migration, "rewrite the orders
API from Go to Python") produced 12 of rac's 13 failures precisely because its
vocabulary saturates PEP titles. To test whether that collapse is intrinsic or
an artifact of one over-lexical scenario, the synthetic bank grades scenarios
by overlap band — and this module makes the band a MEASURED property, not just
a label.

The measure is frequency-weighted: for each salient task token, its document
frequency across PEP titles (how many titles contain it) — averaged over the
task's tokens. A plain presence test does not discriminate (the 644-title
vocabulary is so broad that almost any technical token appears in *some*
title); weighting by how many titles a token saturates recovers the topical
density the retriever actually sees. A test asserts each scenario's declared
`lexical_overlap` matches its measured band.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from scenarios.loader import Scenario
from scoring.crossover import _domain_tokens

_ROOT = Path(__file__).resolve().parent.parent
_PEP_POOL_PROVENANCE = _ROOT / "scenarios_real" / "peps_pool" / "provenance.json"
_TOKEN = re.compile(r"[a-z0-9]+")

# Overlap-band thresholds on the frequency-weighted score. Calibrated so the
# existing scenarios land where the pilot's failure analysis places them:
# prohibition_language_migration (~0.022, Python/language/rewrite vocab) is the
# clear "high" anchor; the retry/handler/supersession scenarios (~0.003-0.004)
# sit in low. The medium band is the deliberately-authored middle.
HIGH_MIN = 0.012
MEDIUM_MIN = 0.006


@lru_cache(maxsize=2)
def _title_doc_freq(provenance_path: str) -> tuple[dict, int]:
    """Per-token document frequency across PEP titles + the title count.
    Offline: the pool's provenance.json is committed even though its corpora
    are gitignored."""
    provenance = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
    titles = [(e.get("title") or "").lower() for e in provenance.get("peps", [])]
    df: Counter = Counter()
    for title in titles:
        for tok in {t for t in _TOKEN.findall(title) if len(t) > 2}:
            df[tok] += 1
    return dict(df), len(titles)


def pep_title_doc_freq(provenance_path: Path | None = None) -> tuple[dict, int]:
    path = provenance_path or _PEP_POOL_PROVENANCE
    return _title_doc_freq(str(path))


def measured_overlap(scenario: Scenario, doc_freq: tuple[dict, int] | None = None) -> float:
    """Frequency-weighted overlap: mean over the scenario's salient task tokens
    of each token's PEP-title document frequency (fraction of titles containing
    it). 0.0 when the task has no salient tokens."""
    df, n_titles = pep_title_doc_freq() if doc_freq is None else doc_freq
    toks = _domain_tokens(scenario)
    if not toks or not n_titles:
        return 0.0
    return sum(df.get(t, 0) / n_titles for t in toks) / len(toks)


def overlap_band(score: float) -> str:
    """Map a frequency-weighted overlap score to a band: high | medium | low."""
    if score >= HIGH_MIN:
        return "high"
    if score >= MEDIUM_MIN:
        return "medium"
    return "low"
