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
