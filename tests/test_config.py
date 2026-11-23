from evalkit import load_models, load_prices


def test_roles_present():
    roles = load_models()
    assert {"agent", "judge", "synth"} <= set(roles)


def test_judge_uses_a_different_cheaper_model_than_agent():
    roles = load_models()
    assert roles["judge"].model != roles["agent"].model
    assert "haiku" in roles["judge"].model  # cheaper tier by design (see config/models.toml)


def test_every_configured_model_has_a_price():
    prices = load_prices()
    for role in load_models().values():
        assert role.model in prices
    p = prices["claude-sonnet-5-5"]
    assert p.cost_usd(1_000_000, 0) == 2.0 and p.cost_usd(0, 1_000_000) == 10.0


# --- Generation settings (thinking, effort) --------------------------------------------------------

import json  # noqa: E402

from evalkit.config import apply_generation, load_generation, repo_root  # noqa: E402
from evalkit.fixtures import request_key  # noqa: E402


def test_every_configured_model_sets_thinking_and_effort_explicitly():
    # Sonnet 5.5 and Haiku 5.5 think by default, and thinking counts toward max_tokens; leaving it
    # implicit is how a 1024-token agent ends turns at stop_reason "max_tokens".
    gen = load_generation()
    for role in load_models().values():
        assert "thinking" in gen[role.model] and "effort" in gen[role.model], role.model
    # Each model's own spelling of "thinking off": disabled is a 400 on Sonnet 5.5.
    assert gen["claude-sonnet-5-5"]["thinking"] == {"type": "between_tools"}
    assert gen["claude-haiku-5-5"]["thinking"] == {"type": "disabled"}
    assert gen["claude-haiku-5-5"]["effort"] in {"low", "medium", "high"}  # disabled needs <= high


def test_apply_generation_fills_but_never_overrides():
    req = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": []}
    out = apply_generation(req)
    assert out["thinking"] == {"type": "disabled"} and out["output_config"] == {"effort": "low"}
    assert "thinking" not in req  # a copy, not an edit
    own = apply_generation(
        {**req, "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}
    )
    assert own["thinking"] == {"type": "adaptive"} and own["output_config"] == {"effort": "high"}
    merged = apply_generation({**req, "output_config": {"format": {"type": "json_schema"}}})
    assert merged["output_config"] == {"format": {"type": "json_schema"}, "effort": "low"}
    assert apply_generation({"model": "unknown", "messages": []}) == {
        "model": "unknown",
        "messages": [],
    }


def test_key_is_the_same_with_or_without_the_settings_spelled_out():
    req = {"model": "claude-sonnet-5-5", "max_tokens": 10, "messages": []}
    assert request_key(req) == request_key(apply_generation(req))


def test_every_fixture_is_keyed_with_the_current_generation_settings():
    # scripts/migrate_fixtures_generation.py re-keys them after a [generation] change.
    for path in sorted((repo_root() / "fixtures" / "recorded").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            assert rec["request"] == apply_generation(rec["request"]), path.name
            assert rec["request_sha256"] == request_key(rec["request"], rec.get("trial", 0)), (
                path.name
            )


# --- Record and live modes: only the [live] model -------------------------------------------------

import pytest  # noqa: E402

from evalkit.config import ModelNotAllowedError, check_live_model, load_live, to_live_model  # noqa: E402


def test_live_model_is_haiku_4_and_nothing_bigger_is_allowed():
    live = load_live()
    assert live is not None and live.model == "claude-haiku-4-5"
    for m in live.allowed:
        assert m.startswith("claude-haiku-4"), m
        assert not any(w in m for w in ("opus", "sonnet", "fable", "mythos"))


def test_to_live_model_swaps_the_model_and_its_settings():
    req = {"model": "claude-sonnet-5-5", "max_tokens": 1024, "messages": [],
           "thinking": {"type": "between_tools"}, "output_config": {"effort": "medium"}}  # fmt: skip
    out = to_live_model(req)
    assert out["model"] == "claude-haiku-4-5"
    assert "thinking" not in out and "output_config" not in out  # Haiku 4.5: no effort parameter
    assert req["model"] == "claude-sonnet-5-5"  # a copy
    kept = to_live_model(
        {**req, "output_config": {"effort": "low", "format": {"type": "json_schema"}}}
    )
    assert kept["output_config"] == {"format": {"type": "json_schema"}}


@pytest.mark.parametrize(
    "model", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-haiku-5-5"]
)
def test_check_live_model_refuses_anything_else(model):
    with pytest.raises(ModelNotAllowedError):
        check_live_model({"model": model})


def test_record_and_live_send_only_haiku_4(monkeypatch, tmp_path):
    from evalkit import LLM
    from evalkit.synth import create_many

    sent = []

    class Client:
        class messages:  # noqa: N801
            @staticmethod
            def create(**req):
                sent.append(req["model"])
                return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
                        "usage": {"input_tokens": 1, "output_tokens": 1}, "model": req["model"]}  # fmt: skip

    for mode in ("live", "record"):
        llm = LLM("t", mode=mode, client=Client(), fixtures_dir=tmp_path)
        for model in ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"):
            llm.create(model=model, max_tokens=5, messages=[{"role": "user", "content": "hi"}])
        create_many(llm, {"a": {"model": "claude-sonnet-5-5", "max_tokens": 5, "messages": []}},
                    use_batch=False)  # fmt: skip
    assert sent and set(sent) == {"claude-haiku-4-5"}
    rec = next(iter(LLM("t", mode="replay", fixtures_dir=tmp_path).store.records()))
    assert (
        rec["request"]["model"] == "claude-haiku-4-5"
    )  # recordings are keyed with the model called
