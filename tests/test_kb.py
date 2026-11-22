from mediadoctor.kb import load_kb, tokens


def test_kb_loads_all_docs():
    kb = load_kb()
    assert len(kb.docs) == 8
    assert "README" not in kb.docs


def test_search_is_deterministic_and_relevant():
    kb = load_kb()
    q = "BehindLiveWindowException in a live HLS stream"
    first = [d.id for d in kb.search(q)]
    assert first == [d.id for d in kb.search(q)]
    assert first[0] == "behind-live-window"


def test_tokens_drop_stopwords():
    assert tokens("How do I fix the AV1 decoder?") == ["fix", "av1", "decoder"]
