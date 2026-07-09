"""rac --version provenance: the system under test is recorded in every
report (backend_versions) and crossover envelope (rac_version)."""

import stat
from pathlib import Path

import pytest

from providers.rac import _rac_version, rac_version
from runner.cli import _backend_versions
from scenarios.loader import load_scenarios
from scoring.crossover import build_dataset

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"


@pytest.fixture(autouse=True)
def _fresh_version_cache():
    _rac_version.cache_clear()
    yield
    _rac_version.cache_clear()


def _fake_rac(tmp_path, body):
    p = tmp_path / "rac"
    p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_rac_version_unavailable(monkeypatch):
    monkeypatch.setenv("RAC_BIN", "/nonexistent/rac-binary")
    assert rac_version() is None


def test_rac_version_from_fake_binary(tmp_path, monkeypatch):
    monkeypatch.setenv("RAC_BIN", str(_fake_rac(tmp_path, 'echo "rac 9.9.9"\n')))
    assert rac_version() == "rac 9.9.9"


def test_rac_version_none_on_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("RAC_BIN", str(_fake_rac(tmp_path, "exit 3\n")))
    assert rac_version() is None


def test_rac_version_cached_per_bin(tmp_path, monkeypatch):
    marker = tmp_path / "calls"
    monkeypatch.setenv("RAC_BIN", str(_fake_rac(
        tmp_path, f'echo x >> "{marker}"\necho "rac 1.0"\n')))
    assert rac_version() == "rac 1.0"
    assert rac_version() == "rac 1.0"
    assert len(marker.read_text().splitlines()) == 1


def test_backend_versions_includes_rac_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("RAC_BIN", str(_fake_rac(tmp_path, 'echo "rac 2.0"\n')))
    assert _backend_versions().get("rac") == "rac 2.0"


def test_backend_versions_omits_rac_when_absent(monkeypatch):
    monkeypatch.setenv("RAC_BIN", "/nonexistent/rac-binary")
    assert "rac" not in _backend_versions()


def test_envelope_rac_version_gating(monkeypatch):
    monkeypatch.setenv("RAC_BIN", "/nonexistent/rac-binary")
    ds = build_dataset(load_scenarios(_SCENARIOS),
                       arms=("context_dump", "naive_rag"), ns=(10,))
    assert "rac_version" in ds
    assert ds["rac_version"] is None


def test_envelope_rac_version_recorded_for_rac_arm(tmp_path, monkeypatch):
    """The gate is on the arm list, not on whether the arm's cells succeed —
    with a fake binary the rac cells error out, but provenance still lands."""
    monkeypatch.setenv("RAC_BIN", str(_fake_rac(tmp_path, 'echo "rac 3.1"\n')))
    ds = build_dataset(load_scenarios(_SCENARIOS),
                       arms=("context_dump", "rac"), ns=(10,))
    assert ds["rac_version"] == "rac 3.1"
