"""AsDecided Core provenance for the stable rac experimental arms."""

import stat
from pathlib import Path

import pytest

from providers.rac import _core_version, core_version
from runner.cli import _backend_versions
from scenarios.loader import load_scenarios
from scoring.crossover import build_dataset

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"


@pytest.fixture(autouse=True)
def _fresh_version_cache():
    _core_version.cache_clear()
    yield
    _core_version.cache_clear()


def _fake_decided(tmp_path, body):
    p = tmp_path / "decided"
    p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_core_version_unavailable(monkeypatch):
    monkeypatch.setenv("DECIDED_BIN", "/nonexistent/decided-binary")
    assert core_version() is None


def test_core_version_from_fake_binary(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "DECIDED_BIN", str(_fake_decided(tmp_path, 'echo "decided 9.9.9"\n'))
    )
    assert core_version() == "decided 9.9.9"


def test_core_version_none_on_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("DECIDED_BIN", str(_fake_decided(tmp_path, "exit 3\n")))
    assert core_version() is None


def test_core_version_cached_per_bin(tmp_path, monkeypatch):
    marker = tmp_path / "calls"
    monkeypatch.setenv("DECIDED_BIN", str(_fake_decided(
        tmp_path, f'echo x >> "{marker}"\necho "decided 1.0"\n')))
    assert core_version() == "decided 1.0"
    assert core_version() == "decided 1.0"
    assert len(marker.read_text().splitlines()) == 1


def test_backend_versions_includes_core_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "DECIDED_BIN", str(_fake_decided(tmp_path, 'echo "decided 2.0"\n'))
    )
    assert _backend_versions().get("asdecided_core") == "decided 2.0"


def test_backend_versions_omits_core_when_absent(monkeypatch):
    monkeypatch.setenv("DECIDED_BIN", "/nonexistent/decided-binary")
    assert "asdecided_core" not in _backend_versions()


def test_envelope_system_under_test_gating(monkeypatch):
    monkeypatch.setenv("DECIDED_BIN", "/nonexistent/decided-binary")
    ds = build_dataset(load_scenarios(_SCENARIOS),
                       arms=("context_dump", "naive_rag"), ns=(10,))
    assert "system_under_test" in ds
    assert ds["system_under_test"] is None


def test_envelope_core_version_recorded_for_rac_arm(tmp_path, monkeypatch):
    """The gate is on the arm list, not on whether the arm's cells succeed —
    with a fake binary the rac cells error out, but provenance still lands."""
    monkeypatch.setenv(
        "DECIDED_BIN", str(_fake_decided(tmp_path, 'echo "decided 3.1"\n'))
    )
    ds = build_dataset(load_scenarios(_SCENARIOS),
                       arms=("context_dump", "rac"), ns=(10,))
    assert ds["system_under_test"] == {
        "product": "AsDecided Core",
        "binary": "decided",
        "version": "decided 3.1",
    }
