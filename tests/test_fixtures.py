import json

import pytest

from evalkit import FixtureMissingError, FixtureStore, request_key
from evalkit.fixtures import KEY_SCHEMA, canonical_json

REQ = {"model": "m", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}


def test_key_is_sha256_hex_and_order_independent():
    k1 = request_key(REQ)
    k2 = request_key(dict(reversed(list(REQ.items()))))
    assert k1 == k2
    assert len(k1) == 64 and all(c in "0123456789abcdef" for c in k1)


def test_key_changes_with_any_field():
    assert request_key(REQ) != request_key({**REQ, "model": "m2"})
    assert request_key(REQ) != request_key({**REQ, "max_tokens": 11})


def test_key_includes_schema_version():
    import hashlib

    expected = hashlib.sha256((KEY_SCHEMA + "\n" + canonical_json(REQ)).encode()).hexdigest()
    assert request_key(REQ) == expected


def test_put_get_roundtrip_and_dedup(tmp_path):
    store = FixtureStore(tmp_path, "ns")
    store.put(REQ, {"content": [{"type": "text", "text": "a"}]})
    store.put(REQ, {"content": [{"type": "text", "text": "b"}]})
    lines = (tmp_path / "ns.jsonl").read_text().splitlines()
    assert len(lines) == 1
    fresh = FixtureStore(tmp_path, "ns")
    assert fresh.get(REQ)["content"][0]["text"] == "b"
    assert json.loads(lines[0])["request_sha256"] == request_key(REQ)


def test_missing_fixture_explains_how_to_rerecord(tmp_path):
    with pytest.raises(FixtureMissingError) as exc:
        FixtureStore(tmp_path, "ns").get(REQ)
    assert "EVALS_LLM_MODE=record" in str(exc.value)


def test_trial_zero_keeps_the_original_key():
    req = {"model": "m", "messages": []}
    assert request_key(req, 0) == request_key(req)
    assert request_key(req, 1) != request_key(req) != request_key(req, 2)


def test_images_are_keyed_by_hash_not_stored(tmp_path):
    from evalkit.fixtures import compact_request

    def req(data: str) -> dict:
        src = {"type": "base64", "media_type": "image/png", "data": data}
        return {
            "model": "m",
            "messages": [{"role": "user", "content": [{"type": "image", "source": src}]}],
        }

    a, b = req("QUJD" * 1000), req("QUJE" * 1000)
    assert request_key(a) != request_key(b)
    small = compact_request(a)
    src = small["messages"][0]["content"][0]["source"]
    assert "data" not in src and src["data_len"] == 4000 and len(src["data_sha256"]) == 64
    assert a["messages"][0]["content"][0]["source"]["data"].startswith("QUJD")  # input untouched
    store = FixtureStore(tmp_path, "img")
    store.put(a, {"content": []})
    assert "QUJD" not in store.path.read_text()
    assert store.get(a) == {"content": []}
    plain = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    assert compact_request(plain) == plain
