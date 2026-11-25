"""Module 3 lab: the 100-trace set replays deterministically and the analyses match the lesson."""

from collections import Counter

import pytest

from evalkit.annotate import (
    first_upstream_counts,
    last_new_mode_at,
    load_annotations,
    load_modes,
    mode_counts,
    rank_modes,
    saturation_curve,
)
from mediadoctor import lab03


@pytest.fixture(scope="module")
def spans():
    return lab03.run_cases()


@pytest.fixture(scope="module")
def traces(spans):
    return lab03.traces_by_case(spans)


@pytest.fixture(scope="module")
def cases():
    return {c["id"]: c for c in lab03.load_cases()}


@pytest.fixture(scope="module")
def ref():
    return load_annotations(lab03.reference_labels_path())


def test_trace_set_shape(spans, traces):
    assert len(traces) == 100 and len(spans) == 592
    cost = sum(lab03.root_of(t)["attributes"]["evalkit.cost.usd"] for t in traces.values())
    assert round(cost, 4) == 0.6313


def test_replay_is_deterministic(spans, traces):
    subset = lab03.run_cases(["m3t001", "m3t033"])
    wanted = {traces["m3t001"][0]["trace_id"], traces["m3t033"][0]["trace_id"]}
    assert subset == [s for s in spans if s["trace_id"] in wanted]


def test_fixtures_record_their_provenance():
    from evalkit import LLM

    records = LLM(namespace=lab03.NAMESPACE).store.records()
    assert len(records) == 200
    assert {r.get("source") for r in records} == {"subagent-authored"}


def test_reference_labels(ref):
    assert len(ref) == 100 and sum(a.failed for a in ref) == 3
    assert {a.annotator for a in ref} == {"reference (subagent-authored, Claude Opus)"}
    counts = mode_counts(ref)
    assert counts == {"fabricated-evidence": 3}  # one mode, one per failing trace
    assert sorted(a.case_id for a in ref if a.failed) == ["m3t010", "m3t072", "m3t088"]


def test_reference_ranking(ref):
    rows = rank_modes(ref, load_modes(lab03.reference_modes_path()))
    # Only modes that occur are ranked: the other eight defined modes have no traces.
    assert len(load_modes(lab03.reference_modes_path())) == 9
    assert [r.mode.id for r in rows] == ["fabricated-evidence"]
    assert [r.priority for r in rows] == [9]  # 3 traces x severity 3


def test_saturation_point(ref):
    curve = saturation_curve(ref)
    assert curve[8] == 0 and last_new_mode_at(curve) == 10 and curve[-1] == 1
    # Stopping after 9 traces would have seen no failure at all; the only mode appears at trace 10.
    assert "fabricated-evidence" not in mode_counts(ref[:9])
    # The first 30 traces hold just 1 of the 3 failures: rare failures need a large sample.
    assert sum(a.failed for a in ref[:30]) == 1


def test_first_upstream(ref):
    c = first_upstream_counts(ref)
    assert c == {"chat:answer": 3}  # every failure starts in the final answer


def test_signals_catch_no_failures(traces, cases, ref):
    table = lab03.signal_table(traces, cases)
    failing = {a.case_id for a in ref if a.failed}
    flagged = {c for c, s in table.items() if s}
    assert flagged == {"m3t080"}  # one format flag, on a passing trace
    assert failing - flagged == failing and len(failing) == 3  # only reading finds these
    assert table["m3t080"] == ["format"]
    assert table["m3t010"] == [] and table["m3t033"] == []


def test_no_tool_errors(traces):
    rows = lab03.tool_error_report(traces)
    assert Counter(r["outcome"] for r in rows) == Counter() and rows == []
    errored = [s for t in traces.values() for s in t if s["status"]["code"] == "ERROR"]
    assert errored == []


def test_retrieval_report(traces, cases):
    rows = lab03.retrieval_report(traces, cases)
    misses = sorted(r["case_id"] for r in rows if not r["hit"])
    assert len(rows) == 53 and misses == []
    ref_miss = {
        a.case_id
        for a in load_annotations(lab03.reference_labels_path())
        if "retrieval-miss" in a.modes
    }
    assert set(misses) == ref_miss


def test_review_layout(traces):
    text = lab03.render_review(traces["m3t033"])
    assert "[2] execute_tool ffprobe      args=" in text and "ERROR" not in text
    assert "[4] retrieval " in text and "Sources: [tool:ffprobe] [kb:mp4-faststart]" in text


def test_annotate_session_is_resumable(traces, tmp_path):
    labels = tmp_path / "labels.csv"
    three = {k: traces[k] for k in ("m3t001", "m3t006", "m3t010")}
    answers = iter(["p", "faststart is fine, points at delivery", "p", "", "q"])
    out = []
    n = lab03.annotate_session(
        three, labels, "me", input_fn=lambda _: next(answers), print_fn=out.append
    )
    assert n == 2
    rows = load_annotations(labels)
    assert [(r.case_id, r.verdict, r.first_upstream) for r in rows] == [
        ("m3t001", "pass", ""),
        ("m3t006", "pass", ""),
    ]
    assert rows[0].trace_id == lab03.root_of(traces["m3t001"])["trace_id"]
    # Resume: only m3t010 is left. Step 4 of its trace is the final answer.
    answers = iter(
        ["f", "states lumen-l3 limits; no tool queried lumen-l3", "4", "made-up-evidence"]
    )
    lab03.annotate_session(
        three, labels, "me", input_fn=lambda _: next(answers), print_fn=out.append
    )
    rows = load_annotations(labels)
    assert rows[-1].case_id == "m3t010" and rows[-1].verdict == "fail"
    assert rows[-1].first_upstream == "chat:answer" and rows[-1].modes == ["made-up-evidence"]


def test_code_session(tmp_path):
    from evalkit.annotate import Annotation, save_annotations

    p = tmp_path / "l.csv"
    save_annotations(p, [Annotation("t1", "fail", note="x"), Annotation("t2", "fail", note="y")])
    answers = iter(["mode-a, mode-b", "q"])
    n = lab03.code_session(
        p, ["mode-a"], input_fn=lambda _: next(answers), print_fn=lambda *a: None
    )
    assert n == 1 and load_annotations(p)[0].modes == ["mode-a", "mode-b"]


def test_cli_rank_writes_outputs(tmp_path, capsys):
    tax, svg = tmp_path / "taxonomy.csv", tmp_path / "pareto.svg"
    assert lab03.main(["rank", "--taxonomy", str(tax), "--svg", str(svg)]) == 0
    out = capsys.readouterr().out
    assert "3 failing" in out and "fabricated-evidence" in out
    assert "ignored-tool-output" not in out  # defined but unused modes are not ranked
    assert tax.read_text().count("\n") == 2 and svg.read_text().startswith("<svg")


def test_cli_compare_reference_with_itself(capsys):
    assert lab03.main(["compare", "--labels", str(lab03.reference_labels_path())]) == 0
    assert "agreement 100%" in capsys.readouterr().out
