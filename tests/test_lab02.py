"""The module 2 lab runs offline and produces the numbers the lesson text quotes."""

import copy
import json

from evalkit import FixtureStore, repo_root
from evalkit.viewer import find_trace, group_traces, summarize_trace
from mediadoctor.lab02 import (
    check_evidence_is_real,
    check_no_repeat_retrieval,
    check_step_budget,
    check_traces,
    load_cases,
    main,
    run_cases,
)
from mediadoctor.toolagent import AGENT_TOOLS_NAMESPACE

FIX = repo_root() / "fixtures" / "recorded" / f"{AGENT_TOOLS_NAMESPACE}.jsonl"


def test_eight_cases_and_all_fixtures_used():
    assert len(load_cases()) == 8
    spans = run_cases()
    assert len(group_traces(spans)) == 8
    llm_calls = sum(1 for s in spans if s["attributes"].get("gen_ai.operation.name") == "chat")
    assert llm_calls == len(FixtureStore(FIX.parent, AGENT_TOOLS_NAMESPACE).records()) == 16
    assert all(n == 2 for n in (summarize_trace(t).llm_calls for t in group_traces(spans).values()))


def test_fixture_provenance_and_latency_recorded():
    for line in FIX.read_text().splitlines():
        rec = json.loads(line)
        assert rec["source"] in {"subagent-authored", "synthetic-authored", "live"}
        assert rec["latency_ms"] > 0


def test_replay_is_byte_for_byte_deterministic():
    assert run_cases() == run_cases()


def test_check_results_match_lesson():
    # The regenerated agent runs are clean: every case passes every trace check.
    res = check_traces(run_cases())
    assert sorted(res) == [f"m2q0{i}" for i in range(1, 9)]
    failing = {
        cid: [n for n, ok in r.items() if not ok] for cid, r in res.items() if not all(r.values())
    }
    assert failing == {}


def _with_failed_ffprobe(trace):
    """A copy of the trace whose ffprobe call is marked as failed (the lesson's what-if)."""
    trace = copy.deepcopy(trace)
    for s in trace:
        if s["name"] == "execute_tool ffprobe":
            s["status"] = {"code": "ERROR", "message": "media file not found"}
    return trace


def _with_repeated_search(trace):
    """A copy of the trace with its chat and retrieval spans repeated three more times."""
    trace = copy.deepcopy(trace)
    extra = [
        s for s in trace if s["attributes"].get("gen_ai.operation.name") in {"chat", "retrieval"}
    ]
    return trace + [copy.deepcopy(s) for s in extra * 3]


def test_trace_checks_catch_the_failures_they_are_built_for():
    spans = run_cases(["m2q03", "m2q08"])
    m2q03, m2q08 = find_trace(spans, "m2q03"), find_trace(spans, "m2q08")
    assert check_evidence_is_real(m2q03)
    assert not check_evidence_is_real(_with_failed_ffprobe(m2q03))
    assert check_no_repeat_retrieval(m2q08) and check_step_budget(m2q08)
    looped = _with_repeated_search(m2q08)
    assert not check_no_repeat_retrieval(looped) and not check_step_budget(looped)


def test_numbers_quoted_in_the_lesson():
    spans = run_cases()
    rows = {s.case_id: s for s in (summarize_trace(t) for t in group_traces(spans).values())}
    total = sum(r.cost_usd for r in rows.values())
    assert round(total, 4) == 0.0506
    top = max(rows.values(), key=lambda r: r.cost_usd)
    assert (top.case_id, round(top.cost_usd, 4)) == ("m2q02", 0.0072)
    assert round(min(r.cost_usd for r in rows.values()) / total, 3) == 0.105
    assert rows["m2q08"].llm_calls == 2 and rows["m2q08"].input_tokens == 1930
    assert round(rows["m2q03"].duration_ms / 1000, 2) == 4.49
    assert round(rows["m2q05"].duration_ms / 1000, 2) == 12.48


def test_no_tool_call_fails_and_m2q03_cites_a_real_probe():
    spans = run_cases()
    tools = [s for s in spans if s["name"].startswith("execute_tool ")]
    assert len(tools) == 18 and all(s["status"]["code"] == "OK" for s in tools)
    trace = find_trace(run_cases(["m2q03"]), "m2q03")
    (tool,) = [s for s in trace if s["name"] == "execute_tool ffprobe"]
    assert json.loads(tool["attributes"]["gen_ai.tool.call.arguments"]) == {
        "file": "progressive_late_moov.mp4"
    }
    root = [s for s in trace if not s["parent_span_id"]][0]
    assert "[tool:ffprobe]" in root["attributes"]["mediadoctor.answer"]
    assert "mdat, moov" in root["attributes"]["mediadoctor.answer"]


def test_cli_run_writes_jsonl(tmp_path, capsys):
    out = tmp_path / "t.jsonl"
    assert main(["run", "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 49
    printed = capsys.readouterr().out
    assert "8 traces" in printed and "total cost $0.0506" in printed
