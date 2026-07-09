"""Signal-to-noise for the crossover.

Ai2's "Signal and Noise" framework (and OpenAI's coding-eval analysis) make the
same point: a benchmark result is only trustworthy when the effect it measures
is large relative to the run-to-run noise. Here the **signal** is the within-seed
paired adherence difference between two arms (`diff_mean` in
`dataset["paired"]`), and the **noise** is that difference's spread across seeds
(`diff_std`, under common random numbers). Their ratio is the signal-to-noise:

    SNR = |diff_mean| / diff_std

An SNR below 1 means the between-arm gap is smaller than the seed-to-seed
wobble — noise-dominated, not a result to lean on. Crucially, **noise cannot be
estimated from a single seed**: with `n_seeds < 2` the SNR is reported as "not
estimable", never as a fabricated number.

Pure and results-neutral: reads only the already-computed `paired` block, adds
nothing to the dataset.
"""

from __future__ import annotations


def _snr_at(diff_mean: float, diff_std: "float | None", n_seeds: int) -> dict:
    """Classify one (pair, N) cell into an SNR record."""
    signal = abs(diff_mean)
    if n_seeds < 2 or diff_std is None:
        # No repeated runs -> noise is unmeasured. The article's core caveat.
        return {"signal": signal, "noise": diff_std, "snr": None,
                "noise_dominated": False, "clean_separation": False,
                "flag": "noise_not_estimable"}
    if diff_std == 0:
        if signal > 0:
            # Every seed gave the same nonzero gap: maximally clean signal.
            return {"signal": signal, "noise": 0.0, "snr": None,
                    "noise_dominated": False, "clean_separation": True,
                    "flag": "zero_noise_clean_separation"}
        # Every seed a perfect tie: no effect and no variance.
        return {"signal": 0.0, "noise": 0.0, "snr": None,
                "noise_dominated": False, "clean_separation": False,
                "flag": "no_effect"}
    snr = signal / diff_std
    return {"signal": signal, "noise": diff_std, "snr": snr,
            "noise_dominated": snr < 1.0, "clean_separation": False, "flag": None}


def signal_to_noise(dataset: dict) -> dict:
    """Signal-to-noise per arm contrast and per N, from `dataset["paired"]`.

    Returns::

        {"n_seeds": int,
         "pairs": {"<a>_vs_<b>": {"by_n": [{"N", "signal", "noise", "snr",
                                            "noise_dominated", "clean_separation",
                                            "flag"}, ...],
                                  "headline_N": int|None,
                                  "headline": <the by_n record at the largest N>|None},
                   ...}}

    `.get`-guarded: a dataset without `paired` (single-arm, legacy, or
    single-contrast) yields an empty `pairs`. The headline is taken at the
    largest N — the buried-in-distractors corpus size where the thesis is
    actually adjudicated.
    """
    paired = dataset.get("paired") or {}
    n_seeds = int(dataset.get("n_seeds", 1) or 1)
    pairs: dict[str, dict] = {}
    for key, series in paired.items():
        by_n = []
        for e in series:
            rec = {"N": e["N"], **_snr_at(e["diff_mean"], e.get("diff_std"), n_seeds)}
            by_n.append(rec)
        headline = max(by_n, key=lambda r: r["N"]) if by_n else None
        pairs[key] = {
            "by_n": by_n,
            "headline_N": headline["N"] if headline else None,
            "headline": headline,
        }
    return {"n_seeds": n_seeds, "pairs": pairs}
