from evalkit import load_models


def test_roles_present():
    roles = load_models()
    assert {"agent", "judge", "synth"} <= set(roles)


def test_judge_uses_a_different_cheaper_model_than_agent():
    roles = load_models()
    assert roles["judge"].model != roles["agent"].model
    assert "haiku" in roles["judge"].model  # cheaper tier by design (see config/models.toml)
