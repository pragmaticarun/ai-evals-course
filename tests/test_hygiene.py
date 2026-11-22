from evalkit.hygiene import cross_split_pairs, ngram_contamination, stale_labels, text_digest


def test_cross_split_pairs():
    texts = {
        "a": "why does the av1 trailer stutter on the atlas phone",
        "b": "why does the av1 trailer stutter on the lumen phone",
        "c": "how do I request audio focus",
    }
    splits = {"a": "gate", "b": "holdout", "c": "holdout"}
    pairs = cross_split_pairs(texts, splits, "gate", "holdout", threshold=0.3)
    assert [(x, y) for x, y, _ in pairs] == [("a", "b")]
    assert (
        cross_split_pairs(texts, {"a": "gate", "b": "gate", "c": "holdout"}, "gate", "holdout")
        == []
    )


def test_ngram_contamination():
    cases = {"t1": "Same offset on every device, so I doubt it's audio sink latency. Help?"}
    corpus = {
        "judge example": "Example: same offset on every device so I doubt it's audio sink latency",
        "prompt": "You are MediaDoctor.",
    }
    hits = ngram_contamination(cases, corpus, n=8)
    assert [(c, s) for c, s, _ in hits] == [("t1", "judge example")]
    assert ngram_contamination(cases, corpus, n=20) == []


def test_stale_labels_and_digest():
    assert text_digest("a  b\nc") == text_digest("a b c")
    labelled = {"v1:a": text_digest("x"), "v1:b": text_digest("y"), "v1:c": text_digest("z")}
    current = {"v1:a": text_digest("x"), "v1:b": text_digest("y, re-recorded")}
    assert stale_labels(labelled, current) == ["v1:b", "v1:c"]
