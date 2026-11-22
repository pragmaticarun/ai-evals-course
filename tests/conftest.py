"""Every test runs offline in replay mode with no API key, exactly like CI."""

import pytest


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("EVALS_LLM_MODE", "replay")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
