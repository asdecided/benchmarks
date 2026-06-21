"""The local web UI server. Skipped when the optional [ui] extra (fastapi) is
not installed — like the real backends, the UI is not a core dependency."""

import json

import pytest

pytest.importorskip("fastapi")  # the [ui] extra; skip the whole module without it
from fastapi.testclient import TestClient  # noqa: E402

from runner.ui import build_ui_app, load_results  # noqa: E402
from tests.test_dashboard import _dataset, _run  # reuse the fixtures  # noqa: E402


def _seed(tmp_path):
    (tmp_path / "2026-01-01-headline.json").write_text(json.dumps(_run()))
    (tmp_path / "crossover_dataset.json").write_text(json.dumps(_dataset()))


def test_index_renders_dashboard_from_latest_results(tmp_path):
    _seed(tmp_path)
    client = TestClient(build_ui_app(tmp_path))
    r = client.get("/")
    assert r.status_code == 200
    assert "Decision Grounding Bench" in r.text and "<svg" in r.text


def test_healthz_and_api_endpoints(tmp_path):
    _seed(tmp_path)
    client = TestClient(build_ui_app(tmp_path))
    h = client.get("/healthz").json()
    assert h["ok"] and h["has_run"]
    assert client.get("/api/run").json()["metrics_by_arm"]["rac"]["adherence_rate"] == 1.0
    assert client.get("/api/crossover").json()["pool_size"] == 644
    assert client.get("/api/cost-curve").json()["naive_rag"]["300"] == 4000


def test_empty_results_dir_shows_guidance(tmp_path):
    client = TestClient(build_ui_app(tmp_path))
    r = client.get("/")
    assert r.status_code == 200 and "No results found" in r.text
    assert client.get("/api/run").status_code == 404


def test_run_endpoints_estimate_status_and_paid_gate(tmp_path, monkeypatch):
    import runner.ui as ui
    monkeypatch.delenv("DG_UI_ALLOW_PAID", raising=False)
    ui._RUN.clear(); ui._RUN.update(state="idle")
    _seed(tmp_path)
    client = TestClient(build_ui_app(tmp_path))

    assert client.get("/api/run/status").json()["state"] == "idle"
    est = client.get("/api/run/estimate?command=compare&arms=rac&ns=10").json()
    assert est["usd"] > 0 and est["calls"] == 2  # 1 arm x 2 seeded scenarios

    # real run is rejected (paid flag not set) — no spend possible from the web
    r = client.post("/api/run/start", json={"mode": "real", "command": "compare"})
    assert r.status_code == 400 and "DG_UI_ALLOW_PAID" in r.json()["error"]


def test_dashboard_shows_run_tab_only_when_live(tmp_path):
    _seed(tmp_path)
    served = TestClient(build_ui_app(tmp_path)).get("/").text
    assert "Run the benchmark" in served and "runOffline()" in served


def test_fragment_endpoint_returns_server_rendered_main(tmp_path):
    _seed(tmp_path)
    client = TestClient(build_ui_app(tmp_path))
    r = client.get("/api/fragment")
    assert r.status_code == 200
    # the <main> inner: tab sections + a server-rendered SVG, no shell
    assert "<section" in r.text and "<svg" in r.text
    assert "<!doctype" not in r.text


def test_fragment_is_204_when_no_results(tmp_path):
    r = TestClient(build_ui_app(tmp_path)).get("/api/fragment")
    assert r.status_code == 204


def test_load_results_picks_newest(tmp_path):
    import time
    (tmp_path / "run-1-compare-x.json").write_text(json.dumps({"runs": [], "metrics_by_arm": {}, "tag": "old"}))
    time.sleep(0.01)
    (tmp_path / "2026-01-01-headline.json").write_text(json.dumps({**_run(), "tag": "new"}))
    run, _ = load_results(tmp_path)
    assert run["tag"] == "new"
