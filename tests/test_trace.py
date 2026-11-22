import json

import pytest

from evalkit import Tracer, VirtualClock, load_jsonl, to_otlp_json
from evalkit.trace import SeededIds, openinference_attributes


def _tracer(seed: str = "t") -> Tracer:
    return Tracer(clock=VirtualClock(1_000), ids=SeededIds(seed))


def test_nesting_ids_and_times():
    tr = _tracer()
    with tr.span("root", {"gen_ai.operation.name": "invoke_agent"}) as root:
        tr.clock.advance(5)
        with tr.span("child", kind="CLIENT") as child:
            tr.clock.advance(10)
    assert child.parent_span_id == root.span_id
    assert child.trace_id == root.trace_id and len(root.trace_id) == 32 and len(root.span_id) == 16
    assert child.duration_ms == 10 and root.duration_ms == 15
    assert root.status_code == "OK" and child.kind == "CLIENT"


def test_exception_marks_error_and_reraises():
    tr = _tracer()
    with pytest.raises(ValueError), tr.span("boom"):
        raise ValueError("bad input")
    (sp,) = tr.finished
    assert sp.status_code == "ERROR" and sp.attributes["error.type"] == "ValueError"
    assert sp.events[0]["name"] == "exception"


def test_none_attributes_are_dropped():
    tr = _tracer()
    with tr.span("x", {"a": None, "b": 1}) as sp:
        pass
    assert sp.attributes == {"b": 1}


def test_seeded_ids_are_reproducible():
    a, b = SeededIds("s"), SeededIds("s")
    assert [a.trace_id(), a.span_id()] == [b.trace_id(), b.span_id()]
    assert SeededIds("other").trace_id() != SeededIds("s").trace_id()


def test_export_and_load_roundtrip(tmp_path):
    tr = _tracer()
    with tr.span("root"):
        with tr.span("child"):
            pass
    path = tr.export_jsonl(tmp_path / "t.jsonl")
    spans = load_jsonl(path)
    assert [s["name"] for s in spans] == ["root", "child"]
    assert spans[0]["resource"] == {"service.name": "mediadoctor"}
    assert spans[1]["parent_span_id"] == spans[0]["span_id"]


def test_otlp_json_shape():
    tr = _tracer()
    with tr.span(
        "chat m",
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.usage.input_tokens": 12,
            "gen_ai.request.model": "m",
            "evalkit.cost.usd": 0.5,
            "flag": True,
            "ids": ["a", "b"],
        },
        kind="CLIENT",
    ):
        pass
    body = to_otlp_json(tr.span_dicts(), openinference=True)
    json.dumps(body)  # serializable
    rs = body["resourceSpans"][0]
    span = rs["scopeSpans"][0]["spans"][0]
    assert span["kind"] == 3 and span["status"]["code"] == 1
    attrs = {a["key"]: a["value"] for a in span["attributes"]}
    assert attrs["gen_ai.usage.input_tokens"] == {"intValue": "12"}
    assert attrs["evalkit.cost.usd"] == {"doubleValue": 0.5}
    assert attrs["flag"] == {"boolValue": True}
    assert attrs["ids"]["arrayValue"]["values"][0] == {"stringValue": "a"}
    assert attrs["openinference.span.kind"] == {"stringValue": "LLM"}
    assert "parentSpanId" not in span


def test_openinference_mapping_for_tool_span():
    span = {
        "attributes": {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "ffprobe",
            "gen_ai.tool.call.arguments": "{}",
            "gen_ai.tool.call.result": "ok",
        }
    }
    oi = openinference_attributes(span)
    assert oi["openinference.span.kind"] == "TOOL" and oi["tool.name"] == "ffprobe"
    assert oi["output.value"] == "ok"
