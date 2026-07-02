"""The agent seam: invocations are built from published contracts only."""
from pathlib import Path

import pytest

from agents import AGENTS
from agents.base import RunSpec
from agents.proofkeeper import ProofkeeperAdapter


def make_spec(workspace: Path, **overrides) -> RunSpec:
    defaults = dict(
        app_name="api-ledger",
        modality="api",
        capability_id="LEDGER-0000000000R1",
        graph_file=Path("/tmp/graph.json"),
        start_url="http://127.0.0.1:1234/",
        base_url="http://127.0.0.1:1234",
        workspace=workspace,
        out_dir=workspace / "generated",
        n=2,
        proxy_base_url="http://127.0.0.1:5678/v1",
    )
    defaults.update(overrides)
    return RunSpec(**defaults)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    cli = tmp_path / "node_modules" / "@itsthelore" / "proofkeeper" / "dist" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("// stub")
    (cli.parent.parent / "package.json").write_text('{"version": "2026.7.1"}')
    return tmp_path


def test_registry_exposes_the_reference_agent():
    assert "proofkeeper" in AGENTS


def test_invocation_uses_the_real_cli_path_never_a_bin_shim(workspace: Path):
    invocation = ProofkeeperAdapter().build(make_spec(workspace))
    assert invocation.argv[0] == "node"
    assert invocation.argv[1].endswith("dist/cli.js")
    assert "--graph-file" in invocation.argv and "--capability" in invocation.argv


def test_model_traffic_routes_through_the_harness_proxy(workspace: Path):
    invocation = ProofkeeperAdapter().build(make_spec(workspace))
    assert invocation.env["OPENAI_BASE_URL"] == "http://127.0.0.1:5678/v1"
    assert "OPENAI_API_KEY" in invocation.env


def test_extension_dir_threads_into_the_published_flag(workspace: Path):
    spec = make_spec(workspace, extension_dir=Path("/apps/ext/extension"))
    invocation = ProofkeeperAdapter().build(spec)
    assert "--extension" in invocation.argv


def test_missing_workspace_install_is_a_clear_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="npm ci"):
        ProofkeeperAdapter().build(make_spec(tmp_path))


def test_version_reads_the_pinned_package(workspace: Path):
    assert ProofkeeperAdapter().version(workspace) == "2026.7.1"
