"""The UI's run-trigger manager: argv whitelist, cost estimate, the paid-run
gate, and the offline spawn (with a faked subprocess — no real run)."""

import types

import pytest

import runner.ui as ui


@pytest.fixture(autouse=True)
def _reset_run(monkeypatch):
    ui._RUN.clear(); ui._RUN.update(state="idle")
    monkeypatch.delenv("DG_UI_ALLOW_PAID", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield
    ui._RUN.clear(); ui._RUN.update(state="idle")


def test_clean_arms_and_ns_reject_junk():
    assert ui._clean_arms(["rac", "evil", "naive_rag"]) == ["rac", "naive_rag"]
    assert ui._clean_arms([]) == ["context_dump", "naive_rag", "no_grounding", "rac"]
    assert ui._clean_ns(["10", "x", "50", "-3"]) == [10, 50]
    assert ui._clean_ns([]) == [10, 50]


def test_argv_is_built_from_whitelist_not_client_strings(tmp_path):
    argv, total = ui._argv_for("real", "compare", ["rac", "naive_rag"], [10], False, tmp_path)
    assert argv[:3] == [ui.sys.executable, "-m", "runner.cli"]
    assert "compare" in argv and "--answering" in argv and "claude" in argv
    assert "voyage:voyage-4-large" in argv
    assert total == 2 * 19
    # crossover uses demo + real distractors and sweeps N
    argv2, total2 = ui._argv_for("real", "crossover", ["rac"], [10, 50], False, tmp_path)
    assert "demo" in argv2 and "real" in argv2 and "--ns" in argv2
    assert total2 == 1 * 19 * (1 + 2)
    # offline uses the free stubs
    argv3, _ = ui._argv_for("offline", "compare", ["rac"], [10], False, tmp_path)
    assert "offline-stub" in argv3 and "local-hash" in argv3


def test_estimate_cost_is_positive_and_scales(tmp_path):
    e1 = ui.estimate_cost(tmp_path, "compare", ["rac"], [10], batch=False)
    e2 = ui.estimate_cost(tmp_path, "crossover", ["rac"], [10, 50], batch=False)
    assert e1["usd"] > 0 and e1["calls"] == 19
    assert e2["calls"] > e1["calls"] and e2["usd"] > e1["usd"]
    # batch halves it
    eb = ui.estimate_cost(tmp_path, "compare", ["rac"], [10], batch=True)
    assert eb["usd"] == pytest.approx(e1["usd"] * 0.5, rel=1e-6)


def test_real_run_blocked_without_paid_flag(tmp_path):
    with pytest.raises(ValueError, match="DG_UI_ALLOW_PAID"):
        ui.start_run(tmp_path, mode="real", command="compare", arms=["rac"], ns=[10], batch=False)


def test_real_run_requires_cost_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_UI_ALLOW_PAID", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with pytest.raises(ValueError, match="cost confirmation required"):
        ui.start_run(tmp_path, mode="real", command="compare", arms=["rac"], ns=[10], batch=False)


def test_offline_run_spawns_and_status_tracks(tmp_path, monkeypatch):
    captured = {}

    class _FakeProc:
        def __init__(self): self._rc = None
        def poll(self): return self._rc

    def fake_popen(argv, cwd=None, stdout=None, stderr=None):
        captured["argv"] = argv
        if stdout is not None:
            stdout.write("started\n"); stdout.flush()
        return _FakeProc()

    monkeypatch.setattr(ui.subprocess, "Popen", fake_popen)
    st = ui.start_run(tmp_path, mode="offline", command="compare", arms=["rac"], ns=[10], batch=False)
    assert st["state"] == "running" and "offline-stub" in captured["argv"]

    # a second run is rejected while one is in progress
    with pytest.raises(ValueError, match="already in progress"):
        ui.start_run(tmp_path, mode="offline", command="compare", arms=["rac"], ns=[10], batch=False)

    # when the process exits 0, status flips to done
    ui._RUN["proc"]._rc = 0
    assert ui.run_status()["state"] == "done"
