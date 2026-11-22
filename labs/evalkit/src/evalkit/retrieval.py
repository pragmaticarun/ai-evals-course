"""Retrieval metrics (module 7): evaluate the search step of a RAG system on its own.

Inputs are a ranked list of retrieved ids (best first) and the relevance labels for one query.
Ids may repeat in the ranking (for example, two chunks from the same section); a repeated id is
counted once by recall and NDCG, so retrieving the same passage twice earns nothing extra.

    recall_at_k       share of the relevant ids found in the top k
    precision_at_k    share of the top k that are relevant
    hit_at_k          1 if any relevant id is in the top k
    reciprocal_rank   1 / rank of the first relevant id (0 if none); its mean over queries is MRR
    ndcg_at_k         graded relevance, discounted by rank, normalised by the ideal ranking

Average any of them over queries, and put a bootstrap interval on the mean with
evalkit.stats.bootstrap_ci (resample queries).
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence


def _top(ranked: Sequence[str], k: int) -> Sequence[str]:
    if k < 1:
        raise ValueError("k must be at least 1")
    return ranked[:k]


def recall_at_k(ranked: Sequence[str], relevant: Collection[str], k: int) -> float:
    if not relevant:
        raise ValueError("a query needs at least one relevant id")
    return len(set(_top(ranked, k)) & set(relevant)) / len(set(relevant))


def precision_at_k(ranked: Sequence[str], relevant: Collection[str], k: int) -> float:
    """Divides by k, so a retriever that returns fewer than k results is not rewarded for it."""
    rel = set(relevant)
    return sum(1 for r in _top(ranked, k) if r in rel) / k


def hit_at_k(ranked: Sequence[str], relevant: Collection[str], k: int) -> float:
    return 1.0 if set(_top(ranked, k)) & set(relevant) else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: Collection[str]) -> float:
    rel = set(relevant)
    for i, r in enumerate(ranked, 1):
        if r in rel:
            return 1 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[str], grades: Mapping[str, float], k: int) -> float:
    """NDCG with gain = grade (for example 2 = answers the query, 1 = related) and a log2 rank
    discount. Each id earns its gain once."""
    seen: set[str] = set()
    dcg = 0.0
    for i, r in enumerate(_top(ranked, k), 1):
        if r in seen:
            continue
        seen.add(r)
        dcg += grades.get(r, 0.0) / math.log2(i + 1)
    ideal = sorted((g for g in grades.values() if g > 0), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, 1))
    return dcg / idcg if idcg else 0.0
