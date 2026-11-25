"""The module 1 lab runs fully offline and produces the numbers the lesson text quotes."""

import json

from evalkit import FixtureStore, repo_root
from mediadoctor import AGENT_NAMESPACE, build_request
from mediadoctor.lab01 import (
    cites_known_doc,
    evaluate,
    has_format,
    load_cases,
    main,
    within_length,
)


def test_twenty_cases():
    cases = load_cases()
    assert len(cases) == 20 and len({c["id"] for c in cases}) == 20


def test_every_request_has_a_fixture_in_both_prompt_versions():
    store = FixtureStore(repo_root() / "fixtures" / "recorded", AGENT_NAMESPACE)
    for case in load_cases():
        for v in ("v1", "v2"):
            assert store.has(build_request(case["query"], v)), (case["id"], v)


def test_fixture_provenance_is_labelled():
    path = repo_root() / "fixtures" / "recorded" / f"{AGENT_NAMESPACE}.jsonl"
    sources = {json.loads(line)["source"] for line in path.read_text().splitlines()}
    assert sources <= {"synthetic-authored", "subagent-authored", "live"}


def test_v1_numbers_match_lesson():
    s = evaluate("v1")["summary"]
    assert s["checks"] == {"format": (20, 20), "cites_kb": (19, 20), "length": (20, 20)}
    assert s["all_pass"] == (19, 20)
    assert s["failing_cases"] == ["q11"]


def test_v2_changes_no_check_outcome_but_shortens_answers():
    a, b = evaluate("v1"), evaluate("v2")
    fa, fb = set(a["summary"]["failing_cases"]), set(b["summary"]["failing_cases"])
    assert fa - fb == set() and fb - fa == set()
    assert a["summary"] == b["summary"] and b["summary"]["all_pass"] == (19, 20)
    # the per-case diff is empty, yet v2 did change every answer: all 20 got shorter
    words = {
        v: {cid: len(out.split()) for cid, out in r["outputs"].items()}
        for v, r in (("v1", a), ("v2", b))
    }
    assert all(words["v2"][cid] < words["v1"][cid] for cid in words["v1"])
    assert max(words["v1"].values()) == 90 and max(words["v2"].values()) == 51


def test_q05_passes_all_code_checks_and_now_matches_the_kb():
    out = evaluate("v1")["outputs"]["q05"]
    assert has_format({}, out) and cites_known_doc({}, out) and within_length({}, out)
    # the checks pass whether or not the claim is true; here the answer gets AV1 right
    assert "software AV1 decoder" in out and "SoC" in out
    assert "requirement" not in out


def test_check_functions():
    good = "Likely cause: x\nNext step: y\nSources: [kb:av-sync]"
    assert has_format({}, good)
    assert not has_format({}, "Next step: y\nLikely cause: x\nSources: z")
    assert cites_known_doc({}, good, {"av-sync"})
    assert not cites_known_doc({}, "Sources: [kb:nope]", {"av-sync"})
    assert not cites_known_doc({}, "Sources: none", {"av-sync"})
    assert within_length({}, "word " * 120) and not within_length({}, "word " * 121)


def test_cli_compare_runs(capsys):
    assert main(["compare", "v1", "v2"]) == 0
    out = capsys.readouterr().out
    assert "fixed by v2:  none" in out
    assert "broken by v2: none" in out
    assert out.count("ALL        19/20   failing: q11") == 2


def test_cli_run_writes_outputs(tmp_path, capsys):
    out = tmp_path / "v1.jsonl"
    assert main(["run", "--prompt", "v1", "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 20
