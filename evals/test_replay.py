"""Record/replay: the release configuration is fully recorded, and the committed baseline is current."""

from mediadoctor import lab08


def test_release_config_is_recorded():
    ids = lab08.ids_in(lab08.tier_splits("code"))
    missing = lab08.preflight(lab08.release_prompt(), ids)
    assert not missing, f"{len(missing)} replay misses: re-record (see the lab) and commit fixtures"


def test_committed_baseline_describes_this_commit(head_code):
    current = lab08.load_baseline().run  # this checkout's evals/baseline.json
    problems = lab08.baseline_problems(head_code, current)
    assert not problems, (
        "behaviour changed: run `uv run mediadoctor-lab08 baseline --write` and commit it\n"
        + "\n".join(problems)
    )
