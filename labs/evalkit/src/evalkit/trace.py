"""evalkit.trace: a small, dependency-free tracer that writes OpenTelemetry-shaped spans.

Why not the OpenTelemetry SDK? For learning, it helps to see every moving part in ~200 lines,
and the course needs byte-for-byte reproducible traces in replay mode (seeded IDs and a virtual
clock), which the SDK does not offer out of the box. The data model is the same as OTel's:
a span has a trace id, span id, parent span id, name, kind, start and end time, status,
attributes, and events. Attribute names follow the OpenTelemetry GenAI semantic conventions
(`gen_ai.*`) where one exists. `to_otlp_json()` converts the spans to OTLP/JSON so any
OTLP-capable backend can ingest them (see docs/modules/02-agent-with-tracing/backends.md).

JSONL export format: one span per line.

    {"trace_id": "...32 hex...", "span_id": "...16 hex...", "parent_span_id": null | "...",
     "name": "chat claude-sonnet-5-5", "kind": "CLIENT",
     "start_time_unix_nano": 1795392000000000000, "end_time_unix_nano": ..., "duration_ms": 812.4,
     "status": {"code": "OK" | "ERROR" | "UNSET", "message": ""},
     "attributes": {"gen_ai.operation.name": "chat", ...},
     "events": [{"name": "...", "time_unix_nano": ..., "attributes": {...}}],
     "resource": {"service.name": "mediadoctor"}}
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

AttrValue = str | bool | int | float | list[str] | list[int] | list[float] | list[bool]

# 2026-11-23T00:00:00Z: the fixed start of every replayed trace, so replay output is stable.
VIRTUAL_EPOCH_NS = 1_795_392_000_000_000_000


# --- Clocks -----------------------------------------------------------------------------------


class WallClock:
    """Real time. `advance()` is a no-op because real work already took real time."""

    virtual = False

    def now_ns(self) -> int:
        return time.time_ns()

    def advance(self, ms: float) -> None:
        return None


class VirtualClock:
    """Simulated time for replay mode: time only moves when told to."""

    virtual = True

    def __init__(self, start_ns: int = VIRTUAL_EPOCH_NS):
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    def advance(self, ms: float) -> None:
        self._now += int(round(ms * 1_000_000))


# --- IDs ----------------------------------------------------------------------------------------


class RandomIds:
    def trace_id(self) -> str:
        return os.urandom(16).hex()

    def span_id(self) -> str:
        return os.urandom(8).hex()


class SeededIds:
    """Deterministic IDs derived from a seed, for reproducible replay traces."""

    def __init__(self, seed: str):
        self.seed = seed
        self._n = 0

    def _next(self, nbytes: int) -> str:
        self._n += 1
        return hashlib.sha256(f"{self.seed}:{self._n}".encode()).hexdigest()[: nbytes * 2]

    def trace_id(self) -> str:
        return self._next(16)

    def span_id(self) -> str:
        return self._next(8)


# --- Spans --------------------------------------------------------------------------------------


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: str
    start_ns: int
    end_ns: int | None = None
    attributes: dict[str, AttrValue] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    status_code: str = "UNSET"
    status_message: str = ""
    _clock: Any = field(default=None, repr=False)

    def set_attribute(self, key: str, value: AttrValue | None) -> None:
        if value is not None:
            self.attributes[key] = value

    def set_attributes(self, attrs: dict[str, AttrValue | None]) -> None:
        for k, v in attrs.items():
            self.set_attribute(k, v)

    def add_event(self, name: str, attributes: dict[str, AttrValue] | None = None) -> None:
        self.events.append(
            {"name": name, "time_unix_nano": self._clock.now_ns(), "attributes": attributes or {}}
        )

    def set_error(self, message: str, error_type: str = "error") -> None:
        self.status_code = "ERROR"
        self.status_message = message
        self.set_attribute("error.type", error_type)
        self.add_event("exception", {"exception.type": error_type, "exception.message": message})

    @property
    def duration_ms(self) -> float:
        end = self.end_ns if self.end_ns is not None else self._clock.now_ns()
        return round((end - self.start_ns) / 1_000_000, 3)

    def to_dict(self, resource: dict[str, AttrValue]) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "start_time_unix_nano": self.start_ns,
            "end_time_unix_nano": self.end_ns,
            "duration_ms": self.duration_ms,
            "status": {"code": self.status_code, "message": self.status_message},
            "attributes": dict(self.attributes),
            "events": list(self.events),
            "resource": dict(resource),
        }


class Tracer:
    def __init__(
        self,
        service_name: str = "mediadoctor",
        clock: WallClock | VirtualClock | None = None,
        ids: RandomIds | SeededIds | None = None,
    ):
        self.clock = clock or WallClock()
        self.ids = ids or RandomIds()
        self.resource: dict[str, AttrValue] = {"service.name": service_name}
        self.finished: list[Span] = []
        self._stack: list[Span] = []

    @classmethod
    def for_replay(cls, seed: str, service_name: str = "mediadoctor") -> Tracer:
        return cls(service_name, clock=VirtualClock(), ids=SeededIds(seed))

    @property
    def current(self) -> Span | None:
        return self._stack[-1] if self._stack else None

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, AttrValue | None] | None = None,
        kind: str = "INTERNAL",
    ) -> Iterator[Span]:
        parent = self.current
        sp = Span(
            trace_id=parent.trace_id if parent else self.ids.trace_id(),
            span_id=self.ids.span_id(),
            parent_span_id=parent.span_id if parent else None,
            name=name,
            kind=kind,
            start_ns=self.clock.now_ns(),
            _clock=self.clock,
        )
        sp.set_attributes(attributes or {})
        self._stack.append(sp)
        try:
            yield sp
        except Exception as exc:
            sp.set_error(str(exc), type(exc).__name__)
            raise
        finally:
            sp.end_ns = self.clock.now_ns()
            if sp.status_code == "UNSET":
                sp.status_code = "OK"
            self._stack.pop()
            self.finished.append(sp)

    def span_dicts(self) -> list[dict[str, Any]]:
        # Sort by start time, then root-first, so files read top to bottom like the run.
        spans = sorted(
            self.finished, key=lambda s: (s.trace_id, s.start_ns, s.parent_span_id is not None)
        )
        return [s.to_dict(self.resource) for s in spans]

    def export_jsonl(self, path: Path | str, append: bool = False) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a" if append else "w", encoding="utf-8") as fh:
            for d in self.span_dicts():
                fh.write(json.dumps(d, sort_keys=True, ensure_ascii=False) + "\n")
        return path


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --- OTLP/JSON ----------------------------------------------------------------------------------

_KIND = {"INTERNAL": 1, "SERVER": 2, "CLIENT": 3, "PRODUCER": 4, "CONSUMER": 5}
_STATUS = {"UNSET": 0, "OK": 1, "ERROR": 2}

# Optional OpenInference attributes, which Phoenix uses to pick icons and detail views.
_OI_KIND = {
    "invoke_agent": "AGENT",
    "chat": "LLM",
    "execute_tool": "TOOL",
    "retrieval": "RETRIEVER",
}


def _any_value(v: Any) -> dict[str, Any]:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}  # OTLP/JSON encodes 64-bit ints as strings
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [_any_value(x) for x in v]}}
    return {"stringValue": str(v)}


def _kv(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": k, "value": _any_value(v)} for k, v in sorted(attrs.items())]


def openinference_attributes(span: dict[str, Any]) -> dict[str, Any]:
    a = span["attributes"]
    out: dict[str, Any] = {}
    kind = _OI_KIND.get(str(a.get("gen_ai.operation.name", "")))
    if kind:
        out["openinference.span.kind"] = kind
    if "gen_ai.request.model" in a:
        out["llm.model_name"] = a["gen_ai.request.model"]
        out["llm.provider"] = a.get("gen_ai.provider.name", "")
    if "gen_ai.usage.input_tokens" in a:
        out["llm.token_count.prompt"] = a["gen_ai.usage.input_tokens"]
        out["llm.token_count.completion"] = a.get("gen_ai.usage.output_tokens", 0)
    if "gen_ai.tool.name" in a:
        out["tool.name"] = a["gen_ai.tool.name"]
        out["input.value"] = a.get("gen_ai.tool.call.arguments", "")
        out["input.mime_type"] = "application/json"
    if "gen_ai.tool.call.result" in a:
        out["output.value"] = a["gen_ai.tool.call.result"]
    return out


def to_otlp_json(spans: list[dict[str, Any]], openinference: bool = False) -> dict[str, Any]:
    """Convert evalkit JSONL spans to an OTLP/JSON ExportTraceServiceRequest body."""
    by_resource: dict[str, list[dict[str, Any]]] = {}
    resources: dict[str, dict[str, Any]] = {}
    for s in spans:
        key = json.dumps(s.get("resource", {}), sort_keys=True)
        by_resource.setdefault(key, []).append(s)
        resources[key] = s.get("resource", {})
    out = []
    for key, group in by_resource.items():
        otlp_spans = []
        for s in group:
            attrs = dict(s["attributes"])
            if openinference:
                attrs.update(openinference_attributes(s))
            span = {
                "traceId": s["trace_id"],
                "spanId": s["span_id"],
                "name": s["name"],
                "kind": _KIND.get(s["kind"], 1),
                "startTimeUnixNano": str(s["start_time_unix_nano"]),
                "endTimeUnixNano": str(s["end_time_unix_nano"]),
                "attributes": _kv(attrs),
                "events": [
                    {
                        "name": e["name"],
                        "timeUnixNano": str(e["time_unix_nano"]),
                        "attributes": _kv(e.get("attributes", {})),
                    }
                    for e in s.get("events", [])
                ],
                "status": {"code": _STATUS[s["status"]["code"]], "message": s["status"]["message"]},
            }
            if s.get("parent_span_id"):
                span["parentSpanId"] = s["parent_span_id"]
            otlp_spans.append(span)
        out.append(
            {
                "resource": {"attributes": _kv(resources[key])},
                "scopeSpans": [
                    {"scope": {"name": "evalkit.trace", "version": "0.2.0"}, "spans": otlp_spans}
                ],
            }
        )
    return {"resourceSpans": out}
