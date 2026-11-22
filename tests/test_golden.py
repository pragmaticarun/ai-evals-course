import pytest

from evalkit.golden import (
    HoldoutAccessError,
    HoldoutGuard,
    build_manifest,
    bump,
    check_manifest,
    ids_digest,
    load_manifest,
    rotate,
    write_manifest,
)


def test_manifest_detects_changed_files_and_splits(tmp_path):
    (tmp_path / "cases.jsonl").write_text('{"id": "a"}\n')
    (tmp_path / "labels.csv").write_text("case_id,verdict\na,pass\n")
    m = build_manifest(
        "golden", "1.0.0", tmp_path, ["labels.csv", "cases.jsonl"], {"gate": ["a", "b"]}
    )
    assert list(m["files"]) == ["cases.jsonl", "labels.csv"]
    path = write_manifest(tmp_path / "manifest.json", m)
    m = load_manifest(path)
    assert check_manifest(m, tmp_path, {"gate": ["b", "a"]}) == []
    (tmp_path / "labels.csv").write_text("case_id,verdict\na,fail\n")
    problems = check_manifest(m, tmp_path, {"gate": ["a"]})
    assert any("labels.csv: changed" in p for p in problems)
    assert any("split 'gate'" in p for p in problems)
    (tmp_path / "cases.jsonl").unlink()
    assert any("cases.jsonl: missing" in p for p in check_manifest(m, tmp_path))


def test_ids_digest_ignores_order_and_duplicates():
    assert ids_digest(["b", "a", "a"]) == ids_digest(["a", "b"])
    assert ids_digest(["a"]) != ids_digest(["a", "b"])


def test_bump():
    assert bump("1.2.3", "major") == "2.0.0"
    assert bump("1.2.3", "minor") == "1.3.0"
    assert bump("1.2.3", "patch") == "1.2.4"


def test_holdout_guard():
    g = HoldoutGuard(frozenset({"t1", "t2"}))
    assert g.check(["d1", "d2"], "gate") == ["d1", "d2"]
    with pytest.raises(HoldoutAccessError):
        g.check(["d1", "t1"], "prompt tuning")
    g.check(["t1", "t2"], "release v2", release=True)
    assert g.looks == 1 and g.log == [("release v2", 2)]


def test_rotate():
    gate, hold = rotate(["g1", "g2"], ["h1", "h2", "h3"], ["f1", "f2"], n=2, seed=1)
    assert len(hold) == 3 and {"f1", "f2"} <= set(hold)
    assert len(gate) == 4 and set(gate) - {"g1", "g2"} <= {"h1", "h2", "h3"}
    assert not set(gate) & set(hold)
    with pytest.raises(ValueError):
        rotate([], ["h1"], ["f1", "f2"], n=2)
