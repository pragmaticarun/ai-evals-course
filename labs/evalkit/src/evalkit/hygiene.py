"""Dataset hygiene (module 8): leakage across splits, contamination, and stale labels.

    cross_split_pairs     near-duplicate cases in two splits that should share nothing
    ngram_contamination   long word n-grams of eval cases that appear in prompts, judge examples,
                          or other text a model or a person tuned against
    stale_labels          labels whose output has changed since it was labelled
    text_digest           the short hash a label stores to pin the output it judged

Similarity is module 4's word-trigram Jaccard (`evalkit.synth.similarity`).
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections.abc import Mapping

from evalkit.synth import jaccard, shingles

_WORD = re.compile(r"[a-z0-9]+")


def text_digest(text: str) -> str:
    """First 16 hex digits of the SHA-256 of the text (whitespace-normalised)."""
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()[:16]


def cross_split_pairs(
    texts: Mapping[str, str],
    splits: Mapping[str, str],
    a: str,
    b: str,
    threshold: float = 0.35,
) -> list[tuple[str, str, float]]:
    """Pairs (case in split a, case in split b, similarity) at or above `threshold`, most similar first."""
    sh = {i: shingles(t) for i, t in texts.items()}
    left = [i for i in texts if splits.get(i) == a]
    right = [i for i in texts if splits.get(i) == b]
    out = []
    for x, y in itertools.product(left, right):
        s = jaccard(sh[x], sh[y])
        if s >= threshold:
            out.append((x, y, round(s, 3)))
    return sorted(out, key=lambda t: -t[2])


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = _WORD.findall(text.lower())
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def ngram_contamination(
    cases: Mapping[str, str], corpus: Mapping[str, str], n: int = 8
) -> list[tuple[str, str, str]]:
    """(case id, corpus source, shared n-gram) for every eval case that shares an n-word run with
    a corpus text. Eight words in a row rarely match by chance; short boilerplate does."""
    grams = {src: _ngrams(text, n) for src, text in corpus.items()}
    out = []
    for cid, text in cases.items():
        mine = _ngrams(text, n)
        for src, theirs in grams.items():
            shared = mine & theirs
            if shared:
                out.append((cid, src, " ".join(sorted(shared)[0])))
    return out


def stale_labels(labelled: Mapping[str, str], current: Mapping[str, str]) -> list[str]:
    """Keys whose output digest changed (or whose output is gone) since they were labelled."""
    return sorted(k for k, d in labelled.items() if current.get(k) != d)
