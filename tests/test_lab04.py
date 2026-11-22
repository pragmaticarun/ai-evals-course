"""Module 4 lab: the synthetic dataset regenerates exactly and feeds the module 2/3 tools."""

import json
from collections import Counter

import pytest

from evalkit import LLM
from evalkit.annotate import load_annotations
from evalkit.synth import file_sha256, pair_coverage, write_jsonl
from mediadoctor import lab03, lab04
from mediadoctor.synth_spec import SYNTH_NAMESPACE, build_synth_request, premise_for


@pytest.fixture(scope="module")
def space():
    return lab04.load_default_space()


@pytest.fixture(scope="module")
def generated(space):
    rows = lab04.generate_queries(lab04.make_tuples(space))
    return rows, *lab04.build_dataset(rows)


@pytest.fixture(scope="module")
def dataset():
    return lab04.load_dataset()


def test_tuples_cover_all_pairs(space):
    tuples = lab04.make_tuples(space)
    assert len(tuples) == 200 and pair_coverage(tuples, space) == (242, 242)
    assert len({json.dumps(t, sort_keys=True) for t in tuples}) == 200


def test_requests_use_the_synth_model_and_spec(space):
    t = lab04.make_tuples(space)[0]
    req = build_synth_request(t)
    assert req["model"].startswith("claude-haiku")
    spec = json.loads(req["messages"][0]["content"])
    assert {k: spec[k] for k in space.names} == t


def test_replay_regenerates_frozen_dataset(generated, dataset, tmp_path):
    _, ds, report = generated
    assert ds == dataset
    out = write_jsonl(tmp_path / "v1.jsonl", ds)
    manifest = json.loads(lab04.manifest_path().read_text())
    assert file_sha256(out) == manifest["sha256"] == file_sha256(lab04.dataset_path())
    assert manifest["count"] == len(ds) == 182
    assert len(report["dropped_as_duplicates"]) == 18 and report["leakage_pairs"] == []
    assert Counter(r["split"] for r in ds) == {"train": 88, "test": 49, "dev": 45}


def test_dataset_rows_are_well_formed(dataset, space):
    for r in dataset:
        assert space.valid({k: r[k] for k in space.names})
        assert r["source"] == "synthetic-authored"
        assert ("premise" in r) == (r["ambiguity"] == "false-premise")
        if r["ambiguity"] == "clear":
            for k in ("file", "device"):
                if k in r:
                    assert r[k] in r["question"]
        if r["ambiguity"] == "missing-detail":
            assert not any(r.get(k, "\0") in r["question"] for k in ("file", "device"))
        if r.get("premise"):
            assert r["premise"].lower().split()[-1] in r["question"].lower()


def test_naive_baseline_misses_slices(space):
    qs = lab04.naive_queries()
    assert len(qs) == 50
    cov = lab04.topic_coverage(qs)
    assert cov["audio-focus"] == 0
    assert not any(lab04.NAMES.search(q) for q in qs)


def test_premise_texts_exist_for_every_topic(space):
    for t in lab04.make_tuples(space):
        if t["ambiguity"] == "false-premise":
            assert premise_for(t, {})  # every topic has at least the no-evidence premise


@pytest.fixture(scope="module")
def m4_traces(dataset):
    spans = lab04.run_slice(lab04.agent_slice(dataset))
    return lab03.traces_by_case(spans)


def test_agent_slice_runs_and_module3_tools_read_it(m4_traces, dataset):
    assert len(m4_traces) == 37
    cases = {c["id"]: c for c in dataset}
    table = lab03.signal_table(m4_traces, cases)
    flagged = {cid for cid, s in table.items() if s}
    ref = {a.case_id: a for a in load_annotations(lab04.dev_reference_path())}
    failing = {cid for cid, a in ref.items() if a.failed}
    assert len(failing) == 12
    # The automatic signals flag only the runs that asked for details (which pass); none of the
    # premise or assumption failures trip a signal. That is the point of reading traces.
    assert flagged and not flagged & failing
    assert all(r["hit"] for r in lab03.retrieval_report(m4_traces, cases))


def test_failure_by_dimension(dataset):
    res = lab04.failure_by_dimension(lab04.dev_reference_path(), dataset, "ambiguity")
    assert res["clear"][:2] == (0, 13)
    assert res["false-premise"][:2] == (9, 18)
    assert res["missing-detail"][:2] == (3, 6)


def test_cli_smoke(capsys):
    for argv in (
        ["dims"],
        ["tuples", "--strategy", "pairwise"],
        ["naive"],
        ["coverage"],
        ["gaps"],
        ["by-dimension", "--dim", "persona"],
    ):
        assert lab04.main(argv) == 0
    out = capsys.readouterr().out
    assert "valid after 9 rules: 1342" in out and "34 tuples, value pairs covered 242/242" in out
    assert "25 generated tuples fill the gaps" in out


def test_synth_fixtures_are_labelled():
    llm = LLM(namespace=SYNTH_NAMESPACE)
    recs = llm.store.records()
    assert len(recs) == 201 and all(r["source"] == "synthetic-authored" for r in recs)


def test_check_finds_the_known_defect(dataset):
    assert lab04.check_queries(dataset) == [("m4q022", "does not mention hdr10_hevc_1080p.mp4")]
    bad = dict(dataset[0], ambiguity="missing-detail")
    assert any("should leave it unstated" in p for _, p in lab04.check_queries([bad]))


def test_lab03_reads_other_case_files(tmp_path, capsys):
    assert (
        lab03.main(
            [
                "signals",
                "--traces",
                str(_write_traces(tmp_path)),
                "--cases",
                str(lab04.dataset_path()),
            ]
        )
        == 0
    )
    assert "flagged 3/37 traces" in capsys.readouterr().out
    ref = str(lab04.dev_reference_path())
    assert lab03.main(["compare", "--labels", ref, "--reference", ref]) == 0
    assert "37 traces in common; pass/fail agreement 100%" in capsys.readouterr().out


def _write_traces(tmp_path):
    from evalkit.synth import write_jsonl

    return write_jsonl(
        tmp_path / "t.jsonl", lab04.run_slice(lab04.agent_slice(lab04.load_dataset()))
    )
