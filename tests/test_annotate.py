"""evalkit.annotate: annotation files, modes, ranking, Pareto, saturation, agreement."""

import pytest

from evalkit.annotate import (
    Annotation,
    compare_verdicts,
    last_new_mode_at,
    load_annotations,
    load_modes,
    mode_counts,
    mode_overlap,
    pareto,
    pareto_svg,
    rank_modes,
    saturation_curve,
    save_annotations,
    uncoded,
    upsert_annotation,
    write_taxonomy_csv,
)

MODES_TOML = """
[[mode]]
id = "a"
name = "Mode A"
definition = "def a"
severity = 3
fixability = "hard"

[[mode]]
id = "b"
name = "Mode B"
definition = "def b"
severity = 1
fixability = "easy"

[[mode]]
id = "c"
name = "Mode C"
definition = "def c"
severity = 3
fixability = "easy"
"""


@pytest.fixture
def modes(tmp_path):
    p = tmp_path / "modes.toml"
    p.write_text(MODES_TOML)
    return load_modes(p)


def ann(cid, modes=(), verdict=None, up=""):
    v = verdict or ("fail" if modes else "pass")
    return Annotation(cid, v, note="n", first_upstream=up, modes=list(modes))


def test_roundtrip_and_upsert(tmp_path):
    p = tmp_path / "labels.csv"
    save_annotations(p, [ann("t1", ["a", "b"]), ann("t2")])
    rows = load_annotations(p)
    assert [r.case_id for r in rows] == ["t1", "t2"] and rows[0].modes == ["a", "b"]
    upsert_annotation(p, ann("t1", ["c"]))
    upsert_annotation(p, ann("t3", ["a"]))
    rows = load_annotations(p)
    assert [r.case_id for r in rows] == ["t1", "t2", "t3"] and rows[0].modes == ["c"]


def test_bad_verdict_is_rejected(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("case_id,verdict\nt1,maybe\n")
    with pytest.raises(ValueError, match="pass or fail"):
        load_annotations(p)


def test_modes_validation(tmp_path):
    p = tmp_path / "m.toml"
    p.write_text('[[mode]]\nid = "x"\nseverity = 5\n')
    with pytest.raises(ValueError, match="severity"):
        load_modes(p)


def test_counts_once_per_trace_and_uncoded():
    anns = [ann("t1", ["a", "a"]), ann("t2", ["a"]), ann("t3", [], verdict="fail"), ann("t4")]
    assert mode_counts(anns) == {"a": 2}
    assert [a.case_id for a in uncoded(anns)] == ["t3"]


def test_rank_by_priority_then_fixability(modes):
    anns = [
        ann("t1", ["a"]),
        ann("t2", ["c"]),
        ann("t3", ["b"]),
        ann("t4", ["b"]),
        ann("t5", ["b"]),
    ]
    rows = rank_modes(anns, modes)
    # All three have priority 3 (1x3, 1x3, 3x1). Ties go to the easier fix, then the larger count:
    # b (easy, 3 traces), c (easy, 1 trace), a (hard).
    assert [r.mode.id for r in rows] == ["b", "c", "a"]
    assert [r.priority for r in rows] == [3, 3, 3]
    assert rows[0].examples == ["t3", "t4", "t5"]


def test_unknown_mode_is_an_error(modes):
    with pytest.raises(ValueError, match="not defined: zzz"):
        rank_modes([ann("t1", ["zzz"])], modes)


def test_pareto_and_outputs(modes, tmp_path):
    anns = [ann("t1", ["a"]), ann("t2", ["a"]), ann("t3", ["c"]), ann("t4")]
    rows = rank_modes(anns, modes)
    assert pareto(rows) == [("a", 2, 2 / 3), ("c", 1, 1.0)]
    csv_text = write_taxonomy_csv(rows, tmp_path / "tax.csv").read_text()
    assert csv_text.splitlines()[0].startswith(
        "rank,id,failure_mode,definition,example_trace_ids,count"
    )
    svg = pareto_svg(rows, tmp_path / "p.svg").read_text()
    assert svg.startswith("<svg") and svg.count("<rect") == 2


def test_saturation():
    anns = [ann("t1", ["a"]), ann("t2"), ann("t3", ["b"]), ann("t4", ["a", "b"]), ann("t5")]
    curve = saturation_curve(anns)
    assert curve == [1, 1, 2, 2, 2]
    assert last_new_mode_at(curve) == 3


def test_compare_and_overlap():
    ref = [ann("t1", ["x"]), ann("t2", ["y"]), ann("t3")]
    mine = [ann("t1", ["mine1"]), ann("t2"), ann("t3", ["mine2"])]
    ag = compare_verdicts(mine, ref)
    assert (ag.common, ag.both_fail, ag.both_pass) == (3, 1, 0)
    assert ag.only_mine_fail == ["t3"] and ag.only_ref_fail == ["t2"]
    assert mode_overlap(mine, ref) == {"x": {"mine1": 1}, "y": {"(pass)": 1}}
