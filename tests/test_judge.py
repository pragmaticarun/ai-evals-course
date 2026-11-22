"""evalkit.judge: specs, prompts, parsing, validation metrics, correction and bootstrap."""

import math

import pytest

from evalkit.judge import (
    Example,
    Item,
    JudgeSpec,
    bootstrap_corrected,
    build_judge_request,
    confusion,
    corrected_pass_rate,
    leakage_problems,
    load_judge,
    parse_verdict,
    render_item,
)


def _spec(**kw):
    base = dict(
        name="t", version="v1", mode="m", criterion="c", pass_def="p", fail_def="f",
        context=("question", "answer"),
    )  # fmt: skip
    return JudgeSpec(**{**base, **kw})


def test_parse_verdict_tolerates_fences_and_flags_garbage():
    v = parse_verdict("a", '```json\n{"critique": "ok", "verdict": "pass"}\n```')
    assert v.passed is True and v.critique == "ok"
    assert parse_verdict("b", '{"critique": "x", "verdict": "FAIL"}').passed is False
    assert parse_verdict("c", "I think it passes").passed is None
    assert parse_verdict("d", '{"verdict": "MAYBE"}').passed is None


def test_confusion_pass_is_positive_and_unparsed_counts_as_fail():
    human = {"a": True, "b": True, "c": False, "d": False, "e": True}
    judged = {"a": True, "b": False, "c": False, "d": True, "e": None}
    c = confusion(human, judged)
    assert (c.tp, c.fn, c.tn, c.fp, c.unparsed) == (1, 2, 1, 1, 1)
    assert c.tpr == pytest.approx(1 / 3) and c.tnr == pytest.approx(0.5)
    assert math.isnan(confusion({"a": True}, {"a": True}).tnr)


def test_rogan_gladen():
    # a perfect judge needs no correction
    assert corrected_pass_rate(0.7, 1.0, 1.0) == pytest.approx(0.7)
    # true 0.6, TPR 0.9, TNR 0.8 -> observed 0.6*0.9 + 0.4*0.2 = 0.62
    assert corrected_pass_rate(0.62, 0.9, 0.8) == pytest.approx(0.6)
    assert corrected_pass_rate(0.99, 0.9, 0.8) == 1.0  # clipped
    with pytest.raises(ValueError):
        corrected_pass_rate(0.5, 0.5, 0.5)


def test_bootstrap_is_seeded_and_brackets_the_point():
    labelled = (
        [(True, True)] * 40 + [(True, False)] * 4 + [(False, False)] * 18 + [(False, True)] * 2
    )
    unlabelled = [True] * 70 + [False] * 30
    a = bootstrap_corrected(labelled, unlabelled, draws=500, seed=1)
    b = bootstrap_corrected(labelled, unlabelled, draws=500, seed=1)
    assert a == b and a.low <= a.corrected <= a.high
    assert a.observed == 0.7 and a.draws == 500


def test_render_and_request_use_only_the_declared_context(tmp_path):
    item = Item(
        "x",
        "why?",
        "Likely cause: a\nNext step: b\nSources: none",
        (("ffprobe", "{}", "RESULT", True),),
    )
    assert "RESULT" not in render_item(item, ("question", "answer"))
    assert "RESULT" in render_item(item, ("question", "tools", "answer"))
    spec = _spec(examples=(Example("x", "PASS", "fine"),))
    req = build_judge_request(spec, item, {"x": item})
    assert req["model"].startswith("claude-haiku") and '"verdict": "PASS"' in req["system"]
    assert req["messages"][0]["content"].startswith("<question>")


def test_load_judge_validates(tmp_path):
    p = tmp_path / "j.toml"
    p.write_text(
        'name="a"\nversion="v1"\nmode="m"\ncriterion="c"\npass="p"\nfail="f"\ncontext=["question","logs"]\n'
    )
    with pytest.raises(ValueError, match="context"):
        load_judge(p)
    p.write_text(
        'name="a"\nversion="v1"\nmode="m"\ncriterion="c"\npass="p"\nfail="f"\n[[example]]\ncase_id="q"\nverdict="ok"\ncritique="x"\n'
    )
    with pytest.raises(ValueError, match="verdict"):
        load_judge(p)


def test_leakage_problems():
    spec = _spec(
        examples=(
            Example("q1", "PASS", "fine"),
            Example("q2", "FAIL", "the cause is a missing moov box"),
        )
    )
    probs = leakage_problems(spec, {"q1": "train", "q2": "test"}, ["missing moov box"])
    assert len(probs) == 2 and "test" in probs[0] and "reference text" in probs[1]
    assert leakage_problems(spec, {"q1": "train", "q2": "train"}) == []
