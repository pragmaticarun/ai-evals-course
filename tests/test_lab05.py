"""Module 5 lab: judges and code checks replay deterministically and match the lesson's numbers."""

import pytest

from evalkit.judge import confusion
from mediadoctor import lab05


def test_labelled_set():
    labels = lab05.annotations()
    assert len(labels) == len(lab05.items()) == 137
    sp = lab05.splits()
    assert sum(sp[c] == "train" for c in labels) == 71
    assert sum(sp[c] == "dev" for c in labels) == 37 and sum(sp[c] == "test" for c in labels) == 29
    assert sum(a.failed for a in labels.values()) == 85


def test_few_shot_examples_come_from_train_only():
    sp = lab05.splits()
    for name, versions in lab05.VERSIONS.items():
        for v in versions:
            assert lab05.leakage_problems(lab05.load_spec(name, v), sp) == []


def test_code_checks():
    res = lab05.code_check_results()
    for name in ("format", "citations"):
        c = confusion(*res[name])
        assert c.tpr == 1.0 and c.tnr == 1.0
    inv = confusion(*res["investigated"])
    assert (inv.tn, inv.fp) == (3, 1)  # misses the no-evidence case: see exercise 4


@pytest.mark.parametrize(
    ("name", "version", "split", "expected"),
    [
        ("tool-grounding", "v1", "dev", (26, 1, 2, 4)),
        ("tool-grounding", "v2", "dev", (24, 3, 6, 0)),
        ("tool-grounding", "v2", "test", (18, 2, 3, 2)),
        ("false-premise", "v1", "dev", (26, 2, 4, 5)),
        ("false-premise", "v1", "test", (23, 1, 3, 2)),
        ("next-step", "v1", "dev", (32, 1, 3, 1)),
        ("next-step", "v1", "test", (23, 2, 4, 0)),
    ],
)
def test_judge_validation(name, version, split, expected):
    r = lab05.validate(name, version, split).result
    assert (r.tp, r.fn, r.tn, r.fp) == expected and r.unparsed == 0


def test_train_split_is_refused():
    with pytest.raises(ValueError):
        lab05.validate("next-step", None, "train")


def test_v1_test_split_was_never_run():
    from evalkit import FixtureMissingError

    with pytest.raises(FixtureMissingError):
        lab05.validate("tool-grounding", "v1", "test")


def test_corrected_estimate():
    est, truth, test = lab05.estimate()
    assert est.n_unlabelled == 89 and round(est.observed, 3) == 0.820
    assert round(est.corrected, 3) == 0.840 and round(truth, 3) == 0.876
    assert est.low < truth < est.high


def test_likert_scores():
    dev = lab05.likert_scores("dev")
    assert len(dev) == 37 and set(dev.values()) <= {1, 2, 3, 4, 5}


def test_cli(capsys):
    for argv in (
        ["labels"],
        ["checks"],
        ["validate"],
        ["estimate"],
        ["likert"],
        ["leaks"],
        ["show", "next-step"],
        ["disagreements", "false-premise"],
    ):
        assert lab05.main(argv) == 0
    out = capsys.readouterr().out
    assert "corrected 0.840" in out and "tool-grounding@v2: ok" in out
