"""Module 12: the capstone pipeline, its report, and the self-review check."""

import csv

import pytest

from evalkit import repo_root
from evalkit.golden import HoldoutAccessError
from mediadoctor import capstone as C
from mediadoctor import lab11

PUBLISHED = repo_root() / "docs" / "capstone" / "index.md"


@pytest.fixture(scope="module")
def release_report(tmp_path_factory):
    log = tmp_path_factory.mktemp("cap") / "holdout_log.csv"
    return C.report_markdown(None, release=True, today="2026-11-23", holdout_log=log), log


def test_published_reference_report_is_regenerated_exactly(release_report):
    text, _ = release_report
    assert PUBLISHED.read_text(encoding="utf-8") == text, (
        "docs/capstone/index.md is stale: run `uv run mediadoctor-capstone report --release "
        "--date 2026-11-23 --out docs/capstone/index.md`"
    )


def test_report_follows_the_template(release_report):
    text, _ = release_report
    assert C.check_report(text) == []
    for i, s in enumerate(C.SECTIONS, 1):
        assert f"## {i}. {s}" in text


def test_release_look_is_logged_once_per_report(release_report):
    _, log = release_report
    rows = list(csv.DictReader(log.open(encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["variant"] == "retry" and rows[0]["n"] == "29"


def test_dev_report_does_not_read_the_holdout(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the held-out split was read without --release")

    monkeypatch.setattr(C, "holdout_look", boom)
    text = C.report_markdown("drm-resolution", release=False, today="2026-11-23")
    assert "not spent (dev only)" in text and "Ship `retry` once the held-out look agrees" in text
    with pytest.raises(HoldoutAccessError):
        lab11.task_results("retry", "holdout")


def test_stage_numbers_come_from_the_modules():
    rows = {s.module: s for s in C.stages()}
    assert sorted(rows) == list(range(1, 12))
    assert "16/20" in rows[1].headline
    assert "ignored-tool-output (11)" in rows[3].headline
    assert "TPR 0.90 TNR 0.60" in rows[5].headline
    assert not rows[9].ok  # the monitoring alarm is flagged for the report
    s = C.m11()["summaries"]["retry"]
    assert (s.successes, s.n) == (97, 108)


def test_slices_cover_every_dev_case_and_pick_the_weakest():
    rows = C.slice_rows()
    assert sum(r["n"] for r in rows) == 108
    assert C.weakest_slice() == "audio-focus"
    assert next(r for r in rows if r["topic"] == "audio-focus")["cand"] == 8


def test_unknown_slice_is_rejected():
    with pytest.raises(ValueError, match="unknown topic"):
        C.report_markdown("widevine-l9", today="2026-11-23")


def test_check_report_flags_a_bare_summary():
    text = PUBLISHED.read_text(encoding="utf-8")
    broken = text.replace("## 6. Evaluators", "## 6. Judges").replace("[0.827, 0.942]", "")
    problems = C.check_report(broken)
    assert "missing section: Evaluators" in problems
    assert C.check_report("# empty\n")[:1] == ["missing section: Decision requested"]


def test_cli_run_and_slices(capsys):
    assert C.main(["run"]) == 0
    assert "11 stages replayed; 1 flagged" in capsys.readouterr().out
    assert C.main(["slices"]) == 0
    assert "weakest slice under retry: audio-focus" in capsys.readouterr().out


def test_cli_check_exit_code(tmp_path, capsys):
    bad = tmp_path / "r.md"
    bad.write_text("# r\n## 1. Decision requested\n", encoding="utf-8")
    assert C.main(["check", str(bad)]) == 1
    assert C.main(["check", str(PUBLISHED)]) == 0
