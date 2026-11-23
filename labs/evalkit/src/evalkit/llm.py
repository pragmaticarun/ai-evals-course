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
import time
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from evalkit.config import apply_generation, repo_root
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
        source: str = "live",
        clock: Callable[[], float] = time.perf_counter,
        trial: int = 0,
    ):
        self.mode = Mode(mode or os.environ.get("EVALS_LLM_MODE", Mode.REPLAY))
        self.store = FixtureStore(fixtures_dir or repo_root() / "fixtures" / "recorded", namespace)
        self._client = client
        self.source = source  # provenance label written to fixtures in record mode
        self._clock = clock  # seconds; injectable so synthetic recordings get stable latencies
        # Repeated runs of the same requests (module 6): trial 0 is the ordinary fixture; trials
        # 1, 2, ... are stored under separate keys so each repeat replays its own answer.
        self.trial = trial
        self.calls = 0  # number of real API calls made by this instance
        # Facts about the most recent create() call, read by the tracer (module 2).
        self.last_latency_ms: float | None = None
        self.last_replayed: bool = False

    @property
    def client(self) -> MessagesClient:
        if self._client is None:
            self._client = _default_client()
        return self._client

    def create(self, **request: Any) -> dict[str, Any]:
        """Same arguments as `anthropic.Anthropic().messages.create(...)`.

        The model's generation settings from config/models.toml (thinking, effort) are filled in
        first, so the request that is keyed, recorded, and sent is the one the model really gets.
        """
        request = apply_generation(request)
        if self.mode is Mode.REPLAY:
            rec = self.store.get_record(request, self.trial)
            self.last_latency_ms = rec.get("latency_ms")  # the original call's latency, if known
            self.last_replayed = True
            return rec["response"]
        start = self._clock()
        response = _to_dict(self.client.messages.create(**request))
        self.last_latency_ms = (self._clock() - start) * 1000.0
        self.last_replayed = False
        self.calls += 1
        if self.mode is Mode.RECORD:
            self.store.put(
                request,
                response,
                source=self.source,
                latency_ms=self.last_latency_ms,
                trial=self.trial,
            )
        return response


def text_of(response: dict[str, Any]) -> str:
    """Concatenate the text blocks of a Messages API response."""
    parts = [b.get("text", "") for b in response.get("content", []) if b.get("type") == "text"]
    return "".join(parts)


# Stop reasons that end a turn without a complete answer. An agent loop that treats every
# non-tool_use stop as "the answer" would grade a truncated reply, a policy decline, or a paused
# server-tool turn as if it were finished, so the loops mark these as errors on the trace.
INCOMPLETE_STOPS = {
    "max_tokens": "the reply hit max_tokens and is truncated (thinking counts toward it)",
    "refusal": "the model declined (see stop_details.category)",
    "pause_turn": "a server-tool turn paused and was not resumed",
    "model_context_window_exceeded": "the conversation no longer fits the context window",
}


def incomplete_stop(stop_reason: str | None) -> str | None:
    """A message if `stop_reason` ends the turn without a complete answer, else None."""
    return INCOMPLETE_STOPS.get(str(stop_reason))
