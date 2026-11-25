"""Module 5 lab: judges and code checks replay deterministically and match the lesson's numbers."""

import math

import pytest

from evalkit.judge import confusion
from mediadoctor import lab05


def test_labelled_set():
    labels = lab05.annotations()
    assert len(labels) == len(lab05.items()) == 147
    sp = lab05.splits()
    assert sum(sp[c] == "train" for c in labels) == 89
    assert sum(sp[c] == "dev" for c in labels) == 30 and sum(sp[c] == "test" for c in labels) == 28
    failed = {c for c, a in labels.items() if a.failed}
    assert failed == {"m4q002", "m4q060", "m4q067"} and {sp[c] for c in failed} == {"train"}


def test_few_shot_examples_come_from_train_only():
    sp = lab05.splits()
    for name, versions in lab05.VERSIONS.items():
        for v in versions:
            assert lab05.leakage_problems(lab05.load_spec(name, v), sp) == []


def test_code_checks():
    res = lab05.code_check_results()
    fmt = confusion(*res["format"])
    assert (fmt.tp, fmt.fn, fmt.tn, fmt.fp) == (147, 0, 0, 0) and math.isnan(fmt.tnr)
    cit = confusion(*res["citations"])
    # the one fabricated-evidence trace (m4q067) states its invented caps in prose, not in a citation
    assert (cit.tp, cit.fn, cit.tn, cit.fp) == (146, 0, 0, 1)
    assert res["citations"][1]["m4q067"] is True
    inv = confusion(*res["investigated"])
    assert (inv.tp, inv.fn, inv.tn, inv.fp) == (115, 32, 0, 0)  # 32 false alarms: see exercise 4


@pytest.mark.parametrize(
    ("name", "version", "split", "expected"),
    [
        ("tool-grounding", "v1", "dev", (30, 0, 0, 0)),
        ("tool-grounding", "v2", "dev", (30, 0, 0, 0)),
        ("tool-grounding", "v2", "test", (28, 0, 0, 0)),
        ("false-premise", "v1", "dev", (30, 0, 0, 0)),
        ("false-premise", "v1", "test", (28, 0, 0, 0)),
        ("next-step", "v1", "dev", (30, 0, 0, 0)),
        ("next-step", "v1", "test", (28, 0, 0, 0)),
    ],
)
def test_judge_validation(name, version, split, expected):
    # No dev or test trace is a human FAIL for any judge's mode, so TNR is undefined (0/0).
    r = lab05.validate(name, version, split).result
    assert (r.tp, r.fn, r.tn, r.fp) == expected and r.unparsed == 0
    assert math.isnan(r.tnr)


def test_train_split_is_refused():
    with pytest.raises(ValueError):
        lab05.validate("next-step", None, "train")


def test_v1_test_split_was_never_run():
    from evalkit import FixtureMissingError

    with pytest.raises(FixtureMissingError):
        lab05.validate("tool-grounding", "v1", "test")


def test_corrected_estimate_is_undefined_without_labelled_failures():
    spec = lab05.load_spec("tool-grounding")
    pool = lab05.m3_items()
    unl = lab05.run_spec(spec, list(pool), pool=pool)
    assert len(unl) == 100 and all(v.passed for v in unl.values())  # observed pass rate 1.000
    test = lab05.validate("tool-grounding", None, "test").result
    assert test.tn + test.fp == 0 and math.isnan(test.tnr)
    # With no labelled failures, TNR and so the Rogan-Gladen correction cannot be estimated: the
    # estimate reports the observed rate and says so (nan corrected rate and interval, 0 draws).
    est, _truth, _test = lab05.estimate()
    assert est.observed == 1.0 and est.draws == 0
    assert math.isnan(est.corrected) and math.isnan(est.low) and math.isnan(est.high)


def test_likert_scores():
    dev = lab05.likert_scores("dev")
    assert len(dev) == 30 and set(dev.values()) <= {1, 2, 3, 4, 5}
    assert sorted(dev.values()).count(3) == 1 and sorted(dev.values()).count(5) == 16
    test = lab05.likert_scores("test")
    assert len(test) == 28 and sorted(test.values()).count(5) == 23


def test_cli(capsys):
    for argv in (
        ["labels"],
        ["checks"],
        ["validate"],
        ["likert"],
        ["leaks"],
        ["show", "next-step"],
        ["disagreements", "false-premise"],
    ):
        assert lab05.main(argv) == 0
    out = capsys.readouterr().out
    assert "train  89 traces,  3 failing" in out and "tool-grounding@v2: ok" in out
    assert "TNR nan (0/0)" in out
