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
    assert len(traces) == 100 and len(spans) == 580
    cost = sum(lab03.root_of(t)["attributes"]["evalkit.cost.usd"] for t in traces.values())
    assert round(cost, 4) == 0.5771


def test_replay_is_deterministic(spans, traces):
    subset = lab03.run_cases(["m3t001", "m3t033"])
    wanted = {traces["m3t001"][0]["trace_id"], traces["m3t033"][0]["trace_id"]}
    assert subset == [s for s in spans if s["trace_id"] in wanted]


def test_fixtures_are_labelled_synthetic():
    from evalkit import LLM

    records = LLM(namespace=lab03.NAMESPACE).store.records()
    assert len(records) == 248
    assert {r.get("source") for r in records} == {"synthetic-authored"}


def test_reference_labels(ref):
    assert len(ref) == 100 and sum(a.failed for a in ref) == 52
    assert {a.annotator for a in ref} == {"reference (synthetic-authored)"}
    counts = mode_counts(ref)
    assert counts["ignored-tool-output"] == 11 and counts["format-violation"] == 2
    assert sum(counts.values()) == 60  # 52 failing traces, 8 with two modes


def test_reference_ranking(ref):
    rows = rank_modes(ref, load_modes(lab03.reference_modes_path()))
    assert [r.mode.id for r in rows][:3] == [
        "ignored-tool-output",
        "fabricated-evidence",
        "skipped-investigation",
    ]
    assert [r.priority for r in rows] == [33, 24, 16, 16, 16, 14, 5, 3, 2]


def test_saturation_point(ref):
    curve = saturation_curve(ref)
    assert curve[29] == 6 and last_new_mode_at(curve) == 48 and curve[-1] == 9
    # Stopping at 30 traces would have missed a severity-3 mode first seen at trace 33.
    assert "fabricated-evidence" not in mode_counts(ref[:30])


def test_first_upstream(ref):
    c = first_upstream_counts(ref)
    assert c["chat:answer"] == 24 and c["retrieval"] == 7 and c["chat:plan"] == 13


def test_signals_catch_some_failures_not_all(traces, cases, ref):
    table = lab03.signal_table(traces, cases)
    failing = {a.case_id for a in ref if a.failed}
    flagged = {c for c, s in table.items() if s}
    assert len(flagged) == 34
    assert len(failing - flagged) == 22  # only reading finds these
    assert flagged - failing == {"m3t016", "m3t024", "m3t036", "m3t079"}  # recovered tool errors
    assert table["m3t033"] == ["tool_error", "unrecovered_tool_error", "cites_missing_evidence"]


def test_tool_error_outcomes(traces):
    rows = lab03.tool_error_report(traces)
    assert Counter(r["outcome"] for r in rows) == {"cited anyway": 5, "recovered": 4, "gave up": 3}


def test_retrieval_report(traces, cases):
    rows = lab03.retrieval_report(traces, cases)
    misses = sorted(r["case_id"] for r in rows if not r["hit"])
    assert len(rows) == 63 and len(misses) == 7
    ref_miss = {
        a.case_id
        for a in load_annotations(lab03.reference_labels_path())
        if "retrieval-miss" in a.modes
    }
    assert set(misses) == ref_miss


def test_review_layout(traces):
    text = lab03.render_review(traces["m3t033"])
    assert "[2] execute_tool ffprobe      ERROR" in text and "Sources: [tool:ffprobe]" in text


def test_annotate_session_is_resumable(traces, tmp_path):
    labels = tmp_path / "labels.csv"
    two = {k: traces[k] for k in ("m3t001", "m3t006", "m3t033")}
    answers = iter(["f", "tried a wrong file name, then guessed", "2", "", "p", "", "q"])
    out = []
    n = lab03.annotate_session(
        two, labels, "me", input_fn=lambda _: next(answers), print_fn=out.append
    )
    assert n == 2
    rows = load_annotations(labels)
    assert [(r.case_id, r.verdict, r.first_upstream) for r in rows] == [
        ("m3t001", "fail", "execute_tool ffprobe"),
        ("m3t006", "pass", ""),
    ]
    assert rows[0].trace_id == lab03.root_of(traces["m3t001"])["trace_id"]
    # Resume: only m3t033 is left.
    answers = iter(["f", "cites ffprobe after the call failed", "3", "made-up-evidence"])
    lab03.annotate_session(two, labels, "me", input_fn=lambda _: next(answers), print_fn=out.append)
    rows = load_annotations(labels)
    assert rows[-1].case_id == "m3t033" and rows[-1].first_upstream == "chat:answer"
    assert rows[-1].modes == ["made-up-evidence"]


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
    assert "52 failing" in out and "ignored-tool-output" in out
    assert tax.read_text().count("\n") == 10 and svg.read_text().startswith("<svg")


def test_cli_compare_reference_with_itself(capsys):
    assert lab03.main(["compare", "--labels", str(lab03.reference_labels_path())]) == 0
    assert "agreement 100%" in capsys.readouterr().out
