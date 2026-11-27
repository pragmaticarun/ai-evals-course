import copy

from evalkit.cli import main as evalkit_main
from evalkit.viewer import find_trace, fmt_ms, render_table, render_tree, summarize_trace
from mediadoctor.lab02 import run_cases


def _spans():
    return run_cases(["m2q03", "m2q08"])


def test_fmt_ms():
    assert fmt_ms(45) == "45ms" and fmt_ms(2810) == "2.81s"


def _with_failed_ffprobe(trace):
    """A copy of m2q03 whose ffprobe call failed: the recorded runs have no tool errors."""
    trace = copy.deepcopy(trace)
    for s in trace:
        if s["name"] == "execute_tool ffprobe":
            s["status"] = {"code": "ERROR", "message": "media file not found: 'late_moov.mp4'"}
    return trace


def test_summary_counts_calls_errors_and_cost():
    trace = find_trace(_spans(), "m2q03")
    s = summarize_trace(trace)
    assert (s.llm_calls, s.tool_calls, s.tool_errors, s.status) == (2, 2, 0, "OK")
    assert s.cost_usd > 0
    bad = summarize_trace(_with_failed_ffprobe(trace))
    assert (bad.llm_calls, bad.tool_calls, bad.tool_errors, bad.status) == (2, 2, 1, "ERROR")


def test_tree_shows_nesting_and_errors():
    tree = render_tree(find_trace(_spans(), "m2q08"))
    assert tree.count("execute_tool search_kb") == 1
    assert "└─ retrieval" in tree
    ok = render_tree(find_trace(_spans(), "m2q03"), show_results=True)
    assert "!! ERROR" not in ok and "execute_tool ffprobe" in ok
    err = render_tree(_with_failed_ffprobe(find_trace(_spans(), "m2q03")), show_results=True)
    assert "!! ERROR: media file not found" in err


def test_table_and_cli(tmp_path, capsys):
    spans = _spans()
    assert "2 traces" in render_table(spans)
    import json

    path = tmp_path / "t.jsonl"
    path.write_text("".join(json.dumps(s) + "\n" for s in spans))
    assert evalkit_main(["view", str(path)]) == 0
    assert evalkit_main(["view", str(path), "m2q03", "--all"]) == 0
    assert evalkit_main(["view", str(path), "nope"]) == 2
    assert evalkit_main(["otlp", str(path), "-o", str(tmp_path / "o.json"), "--openinference"]) == 0
    out = json.loads((tmp_path / "o.json").read_text())
    assert len(out["resourceSpans"][0]["scopeSpans"][0]["spans"]) == len(spans)
