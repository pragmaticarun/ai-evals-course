"""Golden data: versioned, hashed, clean, and the held-out split stays held out."""

import pytest

from evalkit.golden import HoldoutAccessError
from mediadoctor import lab08


def test_manifest_matches_the_files():
    problems = lab08.manifest_problems()
    assert not problems, "golden data changed without a new manifest version:\n" + "\n".join(
        problems
    )


def test_splits_do_not_overlap():
    s = lab08.golden_splits()
    assert not set(s["gate"]) & set(s["holdout"])
    assert set(s["judges"]) <= set(s["gate"])


def test_gate_tiers_never_read_the_holdout():
    for tier in lab08.TIERS:
        assert lab08.HOLDOUT_SPLIT not in lab08.tier_splits(tier)
    with pytest.raises(HoldoutAccessError):
        lab08.guard().check(lab08.holdout_ids()[:1], "a tuning script")


def test_no_leakage_or_unreviewed_contamination_or_stale_labels():
    h = lab08.hygiene()
    assert not h.problems, "\n".join(h.problems)
