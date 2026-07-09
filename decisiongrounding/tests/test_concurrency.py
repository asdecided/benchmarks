"""Concurrent crossover: N cells in flight via a thread pool, byte-identical to
sequential. The full real run is ~15h sequentially; concurrency cuts it to a
fraction, and the dataset must not change one byte."""

import json
import threading
import time

import pytest

from scenarios.loader import load_scenarios
from scoring.crossover import build_dataset, build_dataset_multiseed
from util.ratelimit import RateLimiter

_SCENARIOS = "scenarios"
_ARMS = ("context_dump", "naive_rag")


def _canon(ds):
    return json.dumps(ds, sort_keys=True)


def test_concurrent_dataset_is_byte_identical_to_sequential():
    # A small grid: 2 N x 3 discriminating scenarios x 2 arms.
    sc = load_scenarios(_SCENARIOS)
    seq = build_dataset(sc, arms=_ARMS, ns=(10, 50), seed=0, concurrency=1)
    par = build_dataset(sc, arms=_ARMS, ns=(10, 50), seed=0, concurrency=6)
    assert _canon(seq) == _canon(par)


def test_concurrent_multiseed_is_byte_identical():
    sc = load_scenarios(_SCENARIOS)
    seq = build_dataset_multiseed(sc, arms=_ARMS, ns=(10, 50), seeds=[0, 1, 2], concurrency=1)
    par = build_dataset_multiseed(sc, arms=_ARMS, ns=(10, 50), seeds=[0, 1, 2], concurrency=8)
    assert _canon(seq) == _canon(par)


def test_progress_streams_every_cell_under_concurrency():
    # Progress fires once per cell (thread-safe append), for a durable sidecar.
    sc = load_scenarios(_SCENARIOS)
    recs: list = []
    lock = threading.Lock()

    def progress(r):
        with lock:
            recs.append(r)

    build_dataset(sc, arms=_ARMS, ns=(10, 50), seed=0, concurrency=6, progress=progress)
    from scoring.crossover import DISCRIMINATING
    n_disc = len([s for s in sc if s.scenario_type in DISCRIMINATING])
    expected = 2 * len(_ARMS) * n_disc
    assert len(recs) == expected
    assert all(r["record"] == "cell" for r in recs)
    # every (N, arm, scenario) appears exactly once
    keys = {(r["N"], r["arm"], r["scenario_id"]) for r in recs}
    assert len(keys) == expected


def test_rate_limiter_throttles_and_is_thread_safe():
    # 120/min = 2/sec; 5 acquisitions from a drained bucket take >= ~2s.
    limiter = RateLimiter(rpm=120, capacity=1)
    limiter.acquire()  # drain the single burst token
    start = time.monotonic()
    threads = [threading.Thread(target=limiter.acquire) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start
    # 4 tokens at 2/sec after draining the burst -> ~2s (allow slack).
    assert elapsed >= 1.5


def test_rate_limiter_rejects_nonpositive():
    with pytest.raises(ValueError):
        RateLimiter(rpm=0)


def test_cli_concurrency_byte_identical_and_sidecar_uncorrupted(tmp_path):
    from runner.cli import main

    args = ["demo", "--scenarios", _SCENARIOS, "--ns", "10,50", "--seeds", "0-1"]
    seq_dir, par_dir = tmp_path / "seq", tmp_path / "par"
    assert main(args + ["--out", str(seq_dir)]) == 0
    assert main(args + ["--out", str(par_dir), "--concurrency", "6"]) == 0

    a = json.loads((seq_dir / "crossover_dataset.json").read_text())
    b = json.loads((par_dir / "crossover_dataset.json").read_text())
    assert _canon(a) == _canon(b)

    # The sidecar written from worker threads is uncorrupted: every line parses
    # and every cell appears exactly once.
    sidecar = next(par_dir.glob("run-*-crossover.partial.jsonl"))
    lines = [json.loads(ln) for ln in sidecar.read_text().splitlines() if ln.strip()]
    cells = [r for r in lines if r.get("record") == "cell"]
    keys = {(r["seed"], r["N"], r["arm"], r["scenario_id"]) for r in cells}
    assert len(keys) == len(cells)  # no duplicate/interleaved rows
