"""SHA-256 keyed JSONL fixture store for recorded LLM responses.

Each line of fixtures/recorded/<namespace>.jsonl is one JSON object:

    {"request_sha256": "<sha256 hex>", "request": {...}, "response": {...},
     "recorded_at": "2026-11-23T01:30:00+05:30", "source": "live" | "synthetic-authored",
     "latency_ms": 1234.5}            # optional; wall time of the original call

The key is the SHA-256 of the canonical JSON of the request (sorted keys, no
whitespace, UTF-8), prefixed with a schema version. Any change to the model ID,
system prompt, messages, tools, or parameters therefore produces a new key, and a
replay run fails loudly instead of silently reusing a stale answer.

Images (module 7): base64 image data in a request is replaced by its SHA-256 and size before the
request is keyed and stored (`compact_request`). The key still changes when an image changes, but
fixture files do not carry megabytes of base64; the images themselves live in the repo once.

Repeated runs (module 6): the same request sent five times gets five different answers from the
live API, but would share one key. A `trial` number > 0 is mixed into the key (and stored as
"trial" in the record), so trial 0 is the ordinary fixture and trials 1, 2, ... are repeats.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from evalkit.config import apply_generation

KEY_SCHEMA = "evalkit-v1"


class FixtureMissingError(LookupError):
    """Raised in replay mode when no recorded response matches the request."""

    def __init__(self, key: str, namespace: str, path: Path):
        self.key = key
        self.namespace = namespace
        self.path = path
        super().__init__(
            f"No recorded response for request {key[:12]}… in {path}.\n"
            "The request changed (prompt, model ID in config/models.toml, messages, or params) "
            "or was never recorded.\n"
            "Re-record locally with an API key:  EVALS_LLM_MODE=record uv run <your command>\n"
            "CI never calls the API, so commit the updated fixtures file."
        )


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compact_request(obj: Any) -> Any:
    """Replace base64 payloads (image or document sources) with their SHA-256 and byte count."""
    if isinstance(obj, dict):
        if obj.get("type") == "base64" and isinstance(obj.get("data"), str):
            data = obj["data"].encode("ascii")
            rest = {k: compact_request(v) for k, v in obj.items() if k != "data"}
            return {**rest, "data_sha256": hashlib.sha256(data).hexdigest(), "data_len": len(data)}
        return {k: compact_request(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [compact_request(v) for v in obj]
    return obj


def request_key(request: dict[str, Any], trial: int = 0) -> str:
    # The key covers the request as sent: with the model's generation settings (thinking, effort)
    # from config/models.toml filled in, as evalkit.LLM does before every call.
    request = compact_request(apply_generation(request))
    head = KEY_SCHEMA if trial == 0 else f"{KEY_SCHEMA}\ntrial={trial}"
    payload = head + "\n" + canonical_json(request)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FixtureStore:
    """Append-friendly JSONL store; later lines with the same key win."""

    def __init__(self, directory: Path, namespace: str = "default"):
        self.directory = Path(directory)
        self.namespace = namespace
        self.path = self.directory / f"{namespace}.jsonl"
        self._cache: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._cache is None:
            self._cache = {}
            if self.path.exists():
                with self.path.open(encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ValueError(f"{self.path}:{lineno}: invalid JSON: {exc}") from exc
                        self._cache[rec["request_sha256"]] = rec
        return self._cache

    def get(self, request: dict[str, Any], trial: int = 0) -> dict[str, Any]:
        return self.get_record(request, trial)["response"]

    def get_record(self, request: dict[str, Any], trial: int = 0) -> dict[str, Any]:
        key = request_key(request, trial)
        rec = self._load().get(key)
        if rec is None:
            raise FixtureMissingError(key, self.namespace, self.path)
        return rec

    def has(self, request: dict[str, Any], trial: int = 0) -> bool:
        return request_key(request, trial) in self._load()

    def put(
        self,
        request: dict[str, Any],
        response: dict[str, Any],
        source: str = "live",
        latency_ms: float | None = None,
        trial: int = 0,
    ) -> str:
        key = request_key(request, trial)
        rec = {
            "request_sha256": key,
            "request": compact_request(apply_generation(request)),
            "response": response,
            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": source,
        }
        if trial:
            rec["trial"] = trial
        if latency_ms is not None:
            rec["latency_ms"] = round(float(latency_ms), 1)
        self.directory.mkdir(parents=True, exist_ok=True)
        records = self._load()
        records[key] = rec
        # Rewrite the file so it stays deduplicated and diff-friendly (one line per key).
        with self.path.open("w", encoding="utf-8") as fh:
            for r in records.values():
                fh.write(canonical_json(r) + "\n")
        return key

    def records(self) -> list[dict[str, Any]]:
        return list(self._load().values())
