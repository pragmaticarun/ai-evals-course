from evalkit.cli import main as evalkit_main
from evalkit.viewer import find_trace, fmt_ms, render_table, render_tree, summarize_trace
from mediadoctor.lab02 import run_cases


def _spans():
    return run_cases(["m2q03", "m2q08"])


def test_fmt_ms():
    assert fmt_ms(45) == "45ms" and fmt_ms(2810) == "2.81s"


def test_summary_counts_errors_and_cost():
    s = summarize_trace(find_trace(_spans(), "m2q03"))
    assert (s.llm_calls, s.tool_calls, s.tool_errors, s.status) == (2, 1, 1, "ERROR")
    assert s.cost_usd > 0


def test_tree_shows_error_and_nesting():
    tree = render_tree(find_trace(_spans(), "m2q08"))
    assert tree.count("execute_tool search_kb") == 4
    assert "└─ retrieval" in tree
    err = render_tree(find_trace(_spans(), "m2q03"), show_results=True)
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
