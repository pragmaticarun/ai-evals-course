"""The module 2 lab runs offline and produces the numbers the lesson text quotes."""

import json

from evalkit import FixtureStore, repo_root
from evalkit.viewer import find_trace, group_traces, summarize_trace
from mediadoctor.lab02 import check_traces, load_cases, main, run_cases
from mediadoctor.toolagent import AGENT_TOOLS_NAMESPACE

FIX = repo_root() / "fixtures" / "recorded" / f"{AGENT_TOOLS_NAMESPACE}.jsonl"


def test_eight_cases_and_all_fixtures_used():
    assert len(load_cases()) == 8
    spans = run_cases()
    assert len(group_traces(spans)) == 8
    llm_calls = sum(1 for s in spans if s["attributes"].get("gen_ai.operation.name") == "chat")
    assert llm_calls == len(FixtureStore(FIX.parent, AGENT_TOOLS_NAMESPACE).records()) == 22


def test_fixture_provenance_and_latency_recorded():
    for line in FIX.read_text().splitlines():
        rec = json.loads(line)
        assert rec["source"] in {"synthetic-authored", "live"}
        assert rec["latency_ms"] > 0


def test_replay_is_byte_for_byte_deterministic():
    assert run_cases() == run_cases()


def test_check_results_match_lesson():
    res = check_traces(run_cases())
    failing = {
        cid: [n for n, ok in r.items() if not ok] for cid, r in res.items() if not all(r.values())
    }
    assert failing == {
        "m2q03": ["evidence_is_real"],
        "m2q08": ["no_repeat_retrieval", "step_budget"],
    }


def test_numbers_quoted_in_the_lesson():
    spans = run_cases()
    rows = {s.case_id: s for s in (summarize_trace(t) for t in group_traces(spans).values())}
    total = sum(r.cost_usd for r in rows.values())
    assert round(total, 4) == 0.0578
    assert round(rows["m2q08"].cost_usd, 4) == 0.0173
    assert rows["m2q08"].llm_calls == 5 and rows["m2q08"].input_tokens == 7708
    assert round(rows["m2q03"].duration_ms / 1000, 2) == 2.81


def test_failed_tool_call_is_visible_in_trace():
    trace = find_trace(run_cases(["m2q03"]), "m2q03")
    (tool,) = [s for s in trace if s["name"] == "execute_tool ffprobe"]
    assert tool["status"]["code"] == "ERROR"
    assert json.loads(tool["attributes"]["gen_ai.tool.call.arguments"]) == {"file": "late_moov.mp4"}
    root = [s for s in trace if not s["parent_span_id"]][0]
    assert "ffprobe shows" in root["attributes"]["mediadoctor.answer"]


def test_cli_run_writes_jsonl(tmp_path, capsys):
    out = tmp_path / "t.jsonl"
    assert main(["run", "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 53
    printed = capsys.readouterr().out
    assert "8 traces" in printed and "total cost $0.0578" in printed
