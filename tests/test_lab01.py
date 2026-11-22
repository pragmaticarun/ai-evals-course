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
    assert sources <= {"synthetic-authored", "live"}


def test_v1_numbers_match_lesson():
    s = evaluate("v1")["summary"]
    assert s["checks"] == {"format": (19, 20), "cites_kb": (19, 20), "length": (18, 20)}
    assert s["all_pass"] == (16, 20)
    assert s["failing_cases"] == ["q07", "q11", "q15", "q18"]


def test_v2_fixes_two_and_breaks_three():
    a, b = evaluate("v1")["summary"], evaluate("v2")["summary"]
    fa, fb = set(a["failing_cases"]), set(b["failing_cases"])
    assert fa - fb == {"q07", "q18"}
    assert fb - fa == {"q03", "q09", "q14"}
    assert b["all_pass"] == (15, 20)


def test_confident_factual_error_passes_all_code_checks():
    out = evaluate("v1")["outputs"]["q05"]
    assert has_format({}, out) and cites_known_doc({}, out) and within_length({}, out)
    assert "requirement" in out  # the planted, wrong claim the lesson asks students to spot


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
    assert "fixed by v2:  q07, q18" in out
    assert "broken by v2: q03, q09, q14" in out


def test_cli_run_writes_outputs(tmp_path, capsys):
    out = tmp_path / "v1.jsonl"
    assert main(["run", "--prompt", "v1", "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 20
