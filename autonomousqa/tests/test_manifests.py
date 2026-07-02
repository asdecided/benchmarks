"""Every shipped app manifest loads, and the fleet covers all modalities."""
from pathlib import Path

import pytest

from runner.apps import APPS_ROOT, MODALITIES, list_apps, load_manifest


def test_all_apps_load():
    apps = list_apps()
    assert len(apps) >= 3


def test_fleet_spans_every_modality():
    assert {a.modality for a in list_apps()} == set(MODALITIES)


def test_every_app_seeds_an_ambiguous_capability():
    for app in list_apps():
        ambiguous = [c for c in app.capabilities if c.expected == "unverifiable"]
        assert ambiguous, f"{app.name} seeds no deliberately ambiguous capability"
        assert all(c.tier == "ambiguous" for c in ambiguous)


def test_every_app_seeds_a_negative_path():
    for app in list_apps():
        assert any(c.negative for c in app.capabilities), \
            f"{app.name} seeds no negative-path capability"


def test_every_verifiable_capability_has_a_scripted_flow():
    for app in list_apps():
        for cap in app.capabilities:
            flow = app.flow_path(cap.id)
            if cap.expected == "verifiable":
                assert flow.is_file(), f"{app.name}/{cap.id} has no scripted flow"
            else:
                assert not flow.exists(), \
                    f"{app.name}/{cap.id} is seeded unverifiable but has a flow"


def test_capability_ids_are_unique_across_the_fleet():
    seen: set[str] = set()
    for app in list_apps():
        for cap in app.capabilities:
            assert cap.id not in seen, f"duplicate capability id {cap.id}"
            seen.add(cap.id)


def test_manifest_capabilities_match_the_corpus():
    for app in list_apps():
        corpus_ids = set()
        for artifact in (app.corpus / "requirements").glob("*.md"):
            for line in artifact.read_text().splitlines():
                if line.startswith("id: "):
                    corpus_ids.add(line.removeprefix("id: ").strip())
                    break
        assert {c.id for c in app.capabilities} == corpus_ids, app.name


def test_unknown_modality_rejected(tmp_path: Path):
    app_dir = tmp_path / "bogus"
    app_dir.mkdir()
    (app_dir / "app.json").write_text(
        '{"name": "bogus", "modality": "desktop", "summary": "", "frozen": "x",'
        ' "serve": [], "ready_path": "/", "start_path": "/", "corpus": "rac",'
        ' "capabilities": []}')
    with pytest.raises(ValueError, match="modality"):
        load_manifest(app_dir)


def test_extension_app_declares_extension_dir():
    ext = load_manifest(APPS_ROOT / "ext-wordbadge")
    assert ext.extension_dir is not None and (ext.extension_dir / "manifest.json").is_file()
