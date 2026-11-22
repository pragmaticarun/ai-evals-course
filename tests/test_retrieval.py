"""evalkit.retrieval: hand-checked values for every metric."""

import math

import pytest

from evalkit.retrieval import hit_at_k, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank


def test_recall_precision_hit():
    ranked = ["a", "x", "b", "y", "z"]
    assert recall_at_k(ranked, {"a", "b", "c"}, 3) == pytest.approx(2 / 3)
    assert recall_at_k(ranked, {"a", "b", "c"}, 1) == pytest.approx(1 / 3)
    assert precision_at_k(ranked, {"a", "b"}, 5) == pytest.approx(0.4)
    assert precision_at_k(["a"], {"a"}, 5) == pytest.approx(0.2)  # short lists are not rewarded
    assert hit_at_k(ranked, {"y"}, 3) == 0.0
    assert hit_at_k(ranked, {"y"}, 4) == 1.0


def test_duplicates_count_once():
    assert recall_at_k(["a", "a", "a"], {"a", "b"}, 3) == pytest.approx(0.5)
    assert ndcg_at_k(["a", "a"], {"a": 2, "b": 2}, 2) < 1.0


def test_reciprocal_rank():
    assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(["x"], {"a"}) == 0.0


def test_ndcg_by_hand():
    grades = {"a": 2, "b": 1}
    assert ndcg_at_k(["a", "b"], grades, 2) == pytest.approx(1.0)
    dcg = 1 / math.log2(2) + 2 / math.log2(3)
    idcg = 2 / math.log2(2) + 1 / math.log2(3)
    assert ndcg_at_k(["b", "a"], grades, 2) == pytest.approx(dcg / idcg)
    assert ndcg_at_k(["x", "y"], grades, 2) == 0.0


def test_bad_input():
    with pytest.raises(ValueError):
        recall_at_k(["a"], set(), 1)
    with pytest.raises(ValueError):
        precision_at_k(["a"], {"a"}, 0)
