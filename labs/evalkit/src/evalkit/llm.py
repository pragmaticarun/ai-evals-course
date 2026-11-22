"""evalkit.llm: one wrapper for every Claude call in the course.

Modes (EVALS_LLM_MODE, default "replay"):

  replay  Look the request up in the fixture store. Never touches the network and
          needs no API key. A miss raises FixtureMissingError. This is what CI runs.
  record  Call the Anthropic API, then save (or overwrite) the response under the
          request's SHA-256 key. Needs ANTHROPIC_API_KEY in your environment.
  live    Call the API and return the response without saving anything.

Responses are plain dicts in the Messages API shape (`content`, `usage`, `stop_reason`, ...),
so replayed and live responses look identical to the code that consumes them.
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from evalkit.config import repo_root
from evalkit.fixtures import FixtureStore


class Mode(StrEnum):
    REPLAY = "replay"
    RECORD = "record"
    LIVE = "live"


class MessagesClient(Protocol):
    """Anything with `.messages.create(**params)` returning a pydantic model or dict."""

    messages: Any


def _default_client() -> MessagesClient:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Record and live modes call the real API; "
            "put the key in your shell environment or a git-ignored .env file. "
            "Use EVALS_LLM_MODE=replay to run offline from committed fixtures."
        )
    import anthropic  # imported lazily so replay mode never needs network setup

    return anthropic.Anthropic()


def _to_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json", exclude_none=True)
    raise TypeError(f"Unsupported response type: {type(response)!r}")


class LLM:
    def __init__(
        self,
        namespace: str = "default",
        mode: Mode | str | None = None,
        fixtures_dir: Path | None = None,
        client: MessagesClient | None = None,
    ):
        self.mode = Mode(mode or os.environ.get("EVALS_LLM_MODE", Mode.REPLAY))
        self.store = FixtureStore(fixtures_dir or repo_root() / "fixtures" / "recorded", namespace)
        self._client = client
        self.calls = 0  # number of real API calls made by this instance

    @property
    def client(self) -> MessagesClient:
        if self._client is None:
            self._client = _default_client()
        return self._client

    def create(self, **request: Any) -> dict[str, Any]:
        """Same arguments as `anthropic.Anthropic().messages.create(...)`."""
        if self.mode is Mode.REPLAY:
            return self.store.get(request)
        response = _to_dict(self.client.messages.create(**request))
        self.calls += 1
        if self.mode is Mode.RECORD:
            self.store.put(request, response, source="live")
        return response


def text_of(response: dict[str, Any]) -> str:
    """Concatenate the text blocks of a Messages API response."""
    parts = [b.get("text", "") for b in response.get("content", []) if b.get("type") == "text"]
    return "".join(parts)
