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
    assert len(rows) == 1 and rows[0]["variant"] == "v3" and rows[0]["n"] == "28"


def test_dev_report_does_not_read_the_holdout(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the held-out split was read without --release")

    monkeypatch.setattr(C, "holdout_look", boom)
    text = C.report_markdown("drm-resolution", release=False, today="2026-11-23")
    assert "not spent (dev only)" in text and "**Keep `v1`.**" in text
    with pytest.raises(HoldoutAccessError):
        lab11.task_results("retry", "holdout")


def test_stage_numbers_come_from_the_modules():
    rows = {s.module: s for s in C.stages()}
    assert sorted(rows) == list(range(1, 12))
    assert "19/20" in rows[1].headline
    assert "fabricated-evidence (3)" in rows[3].headline
    assert "TPR 1.00 TNR n/a (0/0)" in rows[5].headline  # no failing test traces: TNR is undefined
    # the monitoring alarm is flagged for the report
    assert "manifest problems 0" in rows[8].headline  # lab08 manifest --check is clean
    assert not rows[9].ok and "tool_error CUSUM alarm +8.6 h" in rows[9].headline
    assert "no change kept, v1 stays" in rows[11].headline
    s = C.m11()["summaries"]["v1"]
    assert (s.successes, s.n) == (78, 119)


def test_no_kept_change_keeps_the_baseline_and_labels_the_comparison(release_report):
    text, _ = release_report
    # nothing kept: the report compares v1 with the best rejected configuration on dev
    assert C.candidate() == "v1" and C.comparator() == "v3"
    assert text.startswith("# MediaDoctor eval report: keep `v1` (no change passed its test)")
    assert "Best rejected configuration | `v3`" in text and "| v1 | v3 (rejected) |" in text
    assert "**Keep `v1`.**" in text and "Ship `" not in text
    assert "tool_error CUSUM alarm (+8.6 h after the rollout" in text
    assert "| 1.00 (28/28) | n/a (0/0) |" in text


def test_slices_cover_every_dev_case_and_pick_the_weakest():
    rows = C.slice_rows()
    assert sum(r["n"] for r in rows) == 119
    # drm-resolution and live-stream tie at 0.500 under v1; the tie goes to the first topic by name
    assert C.weakest_slice() == "drm-resolution"
    weakest = next(r for r in rows if r["topic"] == "drm-resolution")
    assert (weakest["n"], weakest["ship"], weakest["cand"]) == (14, 7, 7)
    live = next(r for r in rows if r["topic"] == "live-stream")
    assert live["ship"] / live["n"] == weakest["ship"] / weakest["n"]


def test_unknown_slice_is_rejected():
    with pytest.raises(ValueError, match="unknown topic"):
        C.report_markdown("widevine-l9", today="2026-11-23")


def test_check_report_flags_a_bare_summary():
    text = PUBLISHED.read_text(encoding="utf-8")
    broken = text.replace("## 6. Evaluators", "## 6. Judges").replace("[0.566, 0.735]", "")
    problems = C.check_report(broken)
    assert "missing section: Evaluators" in problems
    assert C.check_report("# empty\n")[:1] == ["missing section: Decision requested"]


def test_cli_run_and_slices(capsys):
    assert C.main(["run"]) == 0
    assert "11 stages replayed; 1 flagged" in capsys.readouterr().out
    assert C.main(["slices"]) == 0
    assert "weakest slice under v1: drm-resolution" in capsys.readouterr().out


def test_cli_check_exit_code(tmp_path, capsys):
    bad = tmp_path / "r.md"
    bad.write_text("# r\n## 1. Decision requested\n", encoding="utf-8")
    assert C.main(["check", str(bad)]) == 1
    assert C.main(["check", str(PUBLISHED)]) == 0
