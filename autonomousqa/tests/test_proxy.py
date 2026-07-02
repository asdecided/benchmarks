"""The scripted model proxy: OpenAI-compatible, deterministic, metered."""
import json
import urllib.request
from pathlib import Path

from runner.apps import APPS_ROOT
from runner.proxy import ModelProxy, load_flow

FLOW = APPS_ROOT / "api-ledger" / "flows" / "LEDGER-0000000000R1.json"


def chat(proxy: ModelProxy, messages: list[dict]) -> dict:
    request = urllib.request.Request(
        f"{proxy.base_url}/chat/completions",
        data=json.dumps({"model": "scripted", "messages": messages,
                         "tools": [], "tool_choice": "auto"}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_scripted_flow_replays_by_assistant_turn():
    flow = load_flow(FLOW, {"base_url": "http://127.0.0.1:9"})
    with ModelProxy("scripted", flow=flow) as proxy:
        first = chat(proxy, [{"role": "system", "content": "s"},
                             {"role": "user", "content": "go"}])
        calls = first["choices"][0]["message"]["tool_calls"]
        assert [c["function"]["name"] for c in calls] == [
            "request", "expect_status", "expect_json"]
        args = json.loads(calls[0]["function"]["arguments"])
        assert args["url"] == "http://127.0.0.1:9/health"

        second = chat(proxy, [{"role": "system", "content": "s"},
                              {"role": "user", "content": "go"},
                              {"role": "assistant", "content": "[...]"},
                              {"role": "user", "content": "results"}])
        assert [c["function"]["name"]
                for c in second["choices"][0]["message"]["tool_calls"]] == ["finish"]

        exhausted = chat(proxy, [{"role": "assistant", "content": "1"},
                                 {"role": "assistant", "content": "2"}])
        assert "tool_calls" not in exhausted["choices"][0]["message"]

        totals = proxy.usage_totals()
        assert totals["requests"] == 3
        assert totals["estimated"] is True
        assert totals["prompt_tokens"] > 0 and totals["completion_tokens"] > 0


def test_scripted_responses_are_deterministic():
    flow = load_flow(FLOW, {"base_url": "http://127.0.0.1:9"})
    transcript = [{"role": "user", "content": "go"}]
    with ModelProxy("scripted", flow=flow) as proxy:
        first = chat(proxy, transcript)
    with ModelProxy("scripted", flow=flow) as proxy:
        second = chat(proxy, transcript)
    assert first["choices"] == second["choices"]


def test_flow_placeholder_substitution_covers_app_dir(tmp_path: Path):
    flow_path = tmp_path / "flow.json"
    flow_path.write_text(json.dumps({
        "capability": "X",
        "turns": [[{"name": "run_command",
                    "arguments": {"command": "python3 {app_dir}/tool.py"}}]],
    }))
    flow = load_flow(flow_path, {"app_dir": "/somewhere/app"})
    assert flow[0][0]["arguments"]["command"] == "python3 /somewhere/app/tool.py"
