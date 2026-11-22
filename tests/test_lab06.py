"""Module 6 lab: the replayed runs, labels, and statistics match the lesson's numbers."""

import pytest

from evalkit import LLM, FixtureMissingError
from evalkit.stats import trial_summary
from mediadoctor import lab05, lab06
from mediadoctor.lab01 import has_format


def test_runs_and_labels_cover_the_plan():
    labs = lab06.labels()
    assert set(labs) == set(lab06.run_keys())
    for prompt, run in lab06.run_keys():
        assert len(labs[(prompt, run)]) == (137 if run == 1 else 37)
        assert set(lab06.items(prompt, run)) == set(labs[(prompt, run)])
    assert sum(lab06.outcomes("v1", 1).values()) == 52
    assert sum(lab06.outcomes("v2", 1).values()) == 59


def test_v1_run_1_is_module_5():
    m5 = lab05.annotations()
    assert {c: frozenset(a.modes) for c, a in m5.items()} == lab06.labels()[("v1", 1)]


def test_format_labels_agree_with_the_code_check():
    for prompt, run in lab06.run_keys():
        labs = lab06.labels()[(prompt, run)]
        for cid, item in lab06.items(prompt, run).items():
            assert has_format({}, item.answer) == ("format-violation" not in labs[cid]), cid


def test_repeats_differ_but_replay_is_stable():
    a = lab06.items("v2", 2)
    b = lab06.items("v2", 3)
    assert sum(a[c].answer != b[c].answer for c in a) > 5
    assert lab06.run_traces("v2", 2) == lab06.run_traces("v2", 2)


def test_unrecorded_trial_fails_loudly():
    with pytest.raises(FixtureMissingError):
        lab06.run_traces("v1", 7, llm=LLM(namespace=lab06.AGENT_NAMESPACE, trial=6))


def test_overall_difference_is_not_significant():
    res = lab06.paired()
    assert (res.a_only, res.b_only) == (19, 26)
    assert res.low < 0 < res.high and res.p_value > 0.3


def test_per_mode_table():
    rows = {r["mode"]: r for r in lab06.mode_table()}
    fp, fmt = rows["accepted-false-premise"], rows["format-violation"]
    assert (fp["v1_fail"], fp["v2_fail"]) == (24, 9) and fp["holm"] < 0.05
    assert (fmt["v1_fail"], fmt["v2_fail"]) == (4, 23) and fmt["holm"] < 0.001
    assert (
        rows["ignored-tool-output"]["paired"].p_value < 0.05 < rows["ignored-tool-output"]["holm"]
    )


def test_variance():
    v1 = trial_summary(lab06.repeated("v1"))
    v2 = trial_summary(lab06.repeated("v2"))
    assert (v1.always_pass, v1.never_pass, v1.flaky) == (10, 12, 15)
    assert (v2.always_pass, v2.never_pass, v2.flaky) == (7, 11, 19)
    assert round(min(v2.run_rates), 3) == 0.378 and round(max(v2.run_rates), 3) == 0.486


def test_vanity_metrics_do_not_separate_pass_from_fail():
    ok = lab06.outcomes("v1", 1)
    h = lab06.helpfulness("v1")
    assert round(lab06.separation({c: float(x) for c, x in h.items()}, ok), 2) == 0.42
    assert round(lab06.separation(lab06.similarity("v1"), ok), 2) == 0.47


def test_report_renders():
    text = lab06.report()
    assert "| format-violation | 0.03 [0.01, 0.07] | 0.17 [0.11, 0.24]" in text
    assert "about 14 points (paired)" in text


def test_cli_smoke(capsys):
    for cmd in (["runs"], ["variance"], ["compare"], ["modes"], ["slices"], ["samples"]):
        assert lab06.main(cmd) == 0
    out = capsys.readouterr().out
    assert "1512 per prompt" in out and "1029 shared queries" in out
