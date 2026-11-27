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
        assert len(labs[(prompt, run)]) == (147 if run == 1 else 30)
        assert set(lab06.items(prompt, run)) == set(labs[(prompt, run)])
    assert sum(lab06.outcomes("v1", 1).values()) == 144
    assert sum(lab06.outcomes("v2", 1).values()) == 144


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
    assert (res.a_only, res.b_only) == (3, 3)
    assert res.diff == 0 and res.low < 0 < res.high and res.p_value > 0.3


def test_per_mode_table_shows_no_mode_changed():
    rows = {r["mode"]: r for r in lab06.mode_table()}
    # Modes that neither prompt failed are left out, including the one v2 targets.
    assert set(rows) == {"assumed-unstated-detail", "fabricated-evidence"}
    assert "accepted-false-premise" not in rows
    assert all(lab06.outcomes(p, 1, "accepted-false-premise").values() for p in lab06.PROMPTS)
    aud, fab = rows["assumed-unstated-detail"], rows["fabricated-evidence"]
    assert (aud["v1_fail"], aud["v2_fail"]) == (1, 1)
    assert (fab["v1_fail"], fab["v2_fail"]) == (1, 2)
    assert all(r["paired"].p_value == 1.0 and r["holm"] == 1.0 for r in rows.values())


def test_variance():
    v1 = trial_summary(lab06.repeated("v1"))
    v2 = trial_summary(lab06.repeated("v2"))
    assert (v1.always_pass, v1.never_pass, v1.flaky) == (25, 0, 5)
    assert (v2.always_pass, v2.never_pass, v2.flaky) == (24, 0, 6)
    assert round(min(v2.run_rates), 3) == 0.867 and round(max(v2.run_rates), 3) == 1.0


def test_vanity_metric_separation_is_unstable_with_three_failures():
    def auc(prompt):
        h = lab06.helpfulness(prompt)
        return round(
            lab06.separation({c: float(x) for c, x in h.items()}, lab06.outcomes(prompt, 1)), 2
        )

    # Three failing answers per prompt: the same judge scores below a coin on v1, well above on v2.
    assert (auc("v1"), auc("v2")) == (0.22, 0.81)
    assert round(lab06.separation(lab06.similarity("v1"), lab06.outcomes("v1", 1)), 2) == 0.28


def test_report_renders():
    text = lab06.report()
    assert "| fabricated-evidence | 0.01 [0.00, 0.04] | 0.01 [0.00, 0.05]" in text
    assert "| v2 | 0.95 | 0.87 to 1.00 | 0.80 | 6 of 30 |" in text
    assert "147 paired queries and 4% discordant pairs" in text


def test_cli_smoke(capsys):
    for cmd in (["runs"], ["variance"], ["compare"], ["modes"], ["slices"], ["samples"]):
        assert lab06.main(cmd) == 0
    out = capsys.readouterr().out
    assert "v1: 0.98 [0.94, 0.99]   v2: 0.98 [0.94, 0.99]" in out
    assert "v1 pass rate 0.98 on 147 queries; v1/v2 discordant share 0.04" in out
    assert "queries for a +/-5-point interval on one rate: 31" in out
