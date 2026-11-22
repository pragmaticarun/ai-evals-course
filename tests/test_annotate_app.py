"""The module 9 annotation app (labs/annotate), tested with FastAPI's TestClient."""

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from annotate import render
from annotate.app import Config, create_app
from annotate.cli import main as cli_main
from annotate.store import load_queue, load_spans, valid_name

MODES = """
[[mode]]
id = "ignored-tool-output"
name = "Answer contradicts tool output"
definition = "The answer contradicts a tool result."
severity = 3

[[mode]]
id = "fabricated-evidence"
name = "Cites evidence it never obtained"
definition = "Cites a tool that failed or never ran."
severity = 3
"""


def span(tid, sid, parent, name, attrs, start, end, error=""):
    return {
        "trace_id": tid,
        "span_id": sid,
        "parent_span_id": parent,
        "name": name,
        "kind": "INTERNAL",
        "start_time_unix_nano": start,
        "end_time_unix_nano": end,
        "duration_ms": (end - start) / 1e6,
        "status": {"code": "ERROR" if error else "UNSET", "message": error},
        "attributes": attrs,
        "events": [],
        "resource": {},
    }


def make_trace(i: int, question: str, answer: str) -> list[dict]:
    tid = f"{i:032x}"
    t0 = 1_000_000_000 * i
    root = {
        "gen_ai.operation.name": "invoke_agent",
        "mediadoctor.case.id": f"r{i:04d}",
        "mediadoctor.question": question,
        "mediadoctor.answer": answer,
        "mediadoctor.steps": 2,
        "mediadoctor.sim.source_case": "m3t999",
    }
    caps = json.dumps(
        {
            "device": "lumen-l3",
            "decoders": [
                {"name": "c2.android.av1.decoder", "hardware": False, "profiles": ["Main"],
                 "max_width": 1920, "max_height": 1080, "max_fps_at_max_size": 30}
            ],
            "android_api_level": 33,
        }
    )  # fmt: skip
    log = json.dumps(
        {
            "log": "x.txt",
            "pattern": "E",
            "matches": 2,
            "lines": ["L3: 10:00 E Codec: boom", "L9: 10:01 W Codec: hmm"],
        }
    )
    kb = json.dumps(
        {
            "results": [
                {"id": "av1-decoding", "title": "AV1 decoding support on Android", "text": "..."}
            ]
        }
    )
    return [
        span(tid, "a1", None, "invoke_agent MediaDoctor", root, t0, t0 + 3_000_000_000),
        span(tid, "a2", "a1", "chat m", {"gen_ai.operation.name": "chat", "gen_ai.usage.input_tokens": 10}, t0, t0 + 1),
        span(tid, "a3", "a1", "execute_tool codec_caps",
             {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "codec_caps",
              "gen_ai.tool.call.arguments": '{"device": "lumen-l3"}', "gen_ai.tool.call.result": caps}, t0 + 2, t0 + 3),
        span(tid, "a4", "a1", "execute_tool ffprobe",
             {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "ffprobe",
              "gen_ai.tool.call.arguments": '{"file": "nope.mp4"}', "gen_ai.tool.call.result": "Error: media file not found"},
             t0 + 4, t0 + 5, error="media file not found: 'nope.mp4'"),
        span(tid, "a5", "a1", "execute_tool logcat_grep",
             {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "logcat_grep",
              "gen_ai.tool.call.arguments": "{}", "gen_ai.tool.call.result": log}, t0 + 6, t0 + 7),
        span(tid, "a6", "a1", "execute_tool search_kb",
             {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "search_kb",
              "gen_ai.tool.call.arguments": "{}", "gen_ai.tool.call.result": kb}, t0 + 8, t0 + 9),
        span(tid, "a7", "a6", "retrieval",
             {"gen_ai.operation.name": "retrieval", "mediadoctor.retrieval.doc_ids": ["av1-decoding"]}, t0 + 8, t0 + 9),
    ]  # fmt: skip


@pytest.fixture
def setup(tmp_path: Path):
    traces = tmp_path / "traces.jsonl"
    answers = [
        "Likely cause: software AV1.\nNext step: serve HEVC.\nSources: [tool:codec_caps] [kb:av1-decoding]",
        "Likely cause: bad file.\nNext step: remux.\nSources: [tool:ffprobe] [tool:logcat_grep] [tool:never_ran]",
        "Likely cause: <script>alert(1)</script>\nNext step: none.\nSources: none",
    ]
    spans = [
        s for i, a in enumerate(answers, 1) for s in make_trace(i, f"question {i} <b>bold</b>", a)
    ]
    traces.write_text("".join(json.dumps(s) + "\n" for s in spans))
    queue = tmp_path / "queue.jsonl"
    queue.write_text(
        "".join(
            json.dumps(
                {
                    "request_id": f"r{i:04d}",
                    "trace_id": f"{i:032x}",
                    "reasons": ["random"],
                    "judge": "PASS",
                }
            )
            + "\n"
            for i in (1, 2, 3)
        )
    )
    modes = tmp_path / "modes.toml"
    modes.write_text(MODES)
    other = tmp_path / "other.csv"
    other.write_text(
        "case_id,verdict,note,first_upstream,modes,annotator\nr0001,pass,,,,b\nr0002,fail,x,,fabricated-evidence,b\nr0003,pass,,,,b\n"
    )
    board = tmp_path / "board.json"
    board.write_text(json.dumps({
        "title": "T", "events": [], "days": [], "alarms": [], "judge": [],
        "chart": {"points": [{"label": "Mon", "rate": 0.01, "lcl": 0, "ucl": 0.04, "status": "ok"},
                             {"label": "Tue", "rate": 0.09, "lcl": 0, "ucl": 0.04, "status": "high"}]},
    }))  # fmt: skip
    cfg = Config(traces, modes, tmp_path / "out", queue, board, {"other": other})
    return cfg, TestClient(create_app(cfg))


def signed_in(client: TestClient, name: str = "ann") -> TestClient:
    r = client.post("/annotator", data={"name": name}, follow_redirects=False)
    assert r.status_code == 303 and "annotator=" in r.headers["set-cookie"]
    client.cookies.set("annotator", name)
    return client


def test_index_and_static(setup):
    _, c = setup
    assert c.get("/healthz").text == "ok"
    r = c.get("/")
    assert r.status_code == 200 and "r0001" in r.text and "not signed in" in r.text
    assert c.get("/static/htmx.min.js").status_code == 200
    assert c.get("/static/keys.js").status_code == 200
    assert c.get("/docs").status_code == 404  # no OpenAPI UI


def test_annotator_names_are_validated(setup):
    _, c = setup
    for bad in ("", "../x", "Has Space", "a" * 40, "other"):
        assert c.post("/annotator", data={"name": bad}, follow_redirects=False).status_code in (
            400,
            422,
        )
    assert valid_name("arun_m-1") and not valid_name("x/y")


def test_review_needs_an_annotator(setup):
    _, c = setup
    assert c.get("/review/0", follow_redirects=False).status_code == 303
    assert c.get("/panel/0").status_code == 401


def test_review_page_renders_the_trace_tree(setup):
    c = signed_in(setup[1])
    r = c.get("/review/1")
    assert r.status_code == 200
    t = r.text
    assert "execute_tool ffprobe" in t and "media file not found" in t  # error span
    assert 'class="cite-bad">[tool:ffprobe]' in t and 'class="cite-ok">[tool:logcat_grep]' in t
    assert 'class="cite-missing">[tool:never_ran]' in t
    assert "c2.android.av1.decoder" in t and "software" in t  # codec_caps view
    assert 'class="lvl-E"' in t and 'class="lvl-W"' in t  # logcat levels
    assert "av1-decoding" in t  # search_kb docs
    assert "mediadoctor.sim" not in t and "m3t999" not in t  # review stays blind
    assert "<b>bold</b>" not in t and "&lt;b&gt;bold&lt;/b&gt;" in t  # escaped
    assert "<kbd>1</kbd> ignored-tool-output" in t
    assert c.get("/review/99").status_code == 404


def test_answer_html_is_escaped(setup):
    c = signed_in(setup[1])
    t = c.get("/review/2").text
    assert "<script>alert(1)</script>" not in t and "&lt;script&gt;" in t


def test_label_validation_and_htmx_flow(setup):
    cfg, c = setup
    c = signed_in(c)
    h = {"HX-Request": "true"}
    r = c.post("/label/0", data={}, headers=h)
    assert "Choose pass" in r.text
    r = c.post("/label/0", data={"verdict": "fail"}, headers=h)
    assert "A fail needs a note or a failure mode" in r.text
    r = c.post("/label/0", data={"verdict": "fail", "modes": "made-up"}, headers=h)
    assert "Unknown failure mode" in r.text
    r = c.post(
        "/label/0",
        data={
            "verdict": "fail",
            "modes": ["ignored-tool-output"],
            "note": "contradicts caps",
            "golden": "1",
        },
        headers=h,
    )
    assert r.status_code == 200 and r.headers["HX-Push-Url"] == "/review/1"
    assert 'id="panel"' in r.text and "<html" not in r.text  # a fragment, not a page
    rows = list(csv.DictReader((cfg.out_dir / "labels-ann.csv").open()))
    assert rows[0]["case_id"] == "r0001" and rows[0]["modes"] == "ignored-tool-output"
    assert rows[0]["annotator"] == "ann" and rows[0]["annotated_at"]
    assert json.loads((cfg.out_dir / "golden-ann.json").read_text()) == ["r0001"]
    # a pass drops any modes sent with it; without HTMX the form redirects to the next unlabelled item
    r = c.post(
        "/label/1",
        data={"verdict": "pass", "modes": ["ignored-tool-output"]},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/review/2"
    rows = list(csv.DictReader((cfg.out_dir / "labels-ann.csv").open()))
    assert rows[1]["verdict"] == "pass" and rows[1]["modes"] == ""
    # relabelling replaces, it does not duplicate; finishing the queue goes back to the index
    r = c.post("/label/0", data={"verdict": "pass"}, headers=h)
    assert r.headers["HX-Push-Url"] == "/review/2"
    r = c.post("/label/2", data={"verdict": "pass"}, headers=h)
    assert r.headers["HX-Redirect"] == "/"
    rows = list(csv.DictReader((cfg.out_dir / "labels-ann.csv").open()))
    assert [x["case_id"] for x in rows] == ["r0001", "r0002", "r0003"]
    assert json.loads((cfg.out_dir / "golden-ann.json").read_text()) == []
    assert "3 / 3" in c.get("/").text


def test_new_failure_mode_during_review(setup):
    cfg, c = setup
    c = signed_in(c)
    r = c.post(
        "/label/0", data={"verdict": "fail", "new_mode": "Bad Id!"}, headers={"HX-Request": "true"}
    )
    assert "lowercase words joined by hyphens" in r.text
    c.post(
        "/label/0",
        data={"verdict": "fail", "new_mode": "unknown-device-guess", "note": 'guessed "specs"'},
    )
    assert 'id = "unknown-device-guess"' in (cfg.out_dir / "modes-added.toml").read_text()
    assert "unknown-device-guess" in c.get("/review/1").text  # now a checkbox
    tax = c.get("/export/taxonomy.csv").text.splitlines()
    assert tax[0].startswith("rank,id,failure_mode") and tax[1].startswith("1,unknown-device-guess")


def test_exports(setup):
    c = signed_in(setup[1])
    c.post("/label/0", data={"verdict": "fail", "modes": ["ignored-tool-output"], "note": "n"})
    c.post("/label/1", data={"verdict": "pass", "golden": "1"})
    labels = c.get("/export/labels.csv")
    assert (
        labels.headers["content-type"].startswith("text/csv")
        and "r0001,00000000000000000000000000000001,fail" in labels.text
    )
    gold = [json.loads(x) for x in c.get("/export/golden.jsonl").text.splitlines()]
    assert {g["case_id"] for g in gold} == {"r0001", "r0002"}
    assert next(g for g in gold if g["case_id"] == "r0002")["flagged"] is True
    assert gold[0]["question"].startswith("question 1") and "Likely cause" in gold[0]["answer"]
    assert c.get("/export/golden-flags.json").json() == ["r0002"]
    assert c.get("/export/labels.csv?annotator=../../etc").status_code == 404
    assert c.get("/export/labels.csv?annotator=other").text.startswith("case_id")


def test_agreement_page(setup):
    c = signed_in(setup[1])
    c.post("/label/0", data={"verdict": "pass"})
    c.post("/label/1", data={"verdict": "fail", "modes": ["fabricated-evidence"], "note": "x"})
    c.post("/label/2", data={"verdict": "fail", "modes": ["ignored-tool-output"], "note": "y"})
    r = c.get("/agreement?a=ann&b=other")
    assert r.status_code == 200
    assert "Cohen&#39;s kappa <b>0.40</b>" in r.text or "Cohen's kappa <b>0.40</b>" in r.text
    assert (
        "Different verdicts (1)" in r.text.replace("DIFFERENT", "Different") and "r0003" in r.text
    )
    assert c.get("/agreement").status_code == 200  # picks the pair with most overlap
    with pytest.raises(ValueError):
        c.app.state.ws.save("other", None, False)  # read-only comparison labels


def test_dashboard(setup):
    cfg, c = setup
    r = c.get("/dashboard")
    assert r.status_code == 200 and "<svg" in r.text and 'class="dot-high"' in r.text
    cfg2 = Config(cfg.traces, cfg.modes, cfg.out_dir, cfg.queue)
    assert TestClient(create_app(cfg2)).get("/dashboard").status_code == 404


def test_queue_file_must_match_traces(setup, tmp_path):
    cfg, _ = setup
    traces = load_spans(cfg.traces)
    assert [it.case_id for it in load_queue(None, traces)] == ["r0001", "r0002", "r0003"]
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"request_id": "x", "trace_id": "f" * 32}) + "\n")
    with pytest.raises(ValueError, match="no trace"):
        load_queue(bad, traces)


def test_render_views_directly(setup):
    cfg, _ = setup
    trace = load_spans(cfg.traces)[f"{1:032x}"]
    nodes = render.tree(trace)
    assert [n.depth for n in nodes] == [0, 1, 1, 1, 1, 1, 2]
    kinds = {n.name: n.view.kind for n in nodes if n.view}
    assert kinds == {
        "execute_tool codec_caps": "decoders",
        "execute_tool ffprobe": "error",
        "execute_tool logcat_grep": "log",
        "execute_tool search_kb": "docs",
    }
    probe = render.tool_view(
        "ffprobe",
        json.dumps(
            {
                "format": "mp4",
                "streams": [
                    {
                        "index": 0,
                        "codec_type": "video",
                        "codec_name": "av1",
                        "width": 640,
                        "height": 360,
                    }
                ],
            }
        ),
        "",
    )
    assert probe.kind == "probe" and probe.rows[0][0][1] == "av1 640x360"
    assert render.tool_view("other", "plain text", "").kind == "text"
    assert render.tool_view("other", '{"a": {"b": 1}}', "").rows == [("a.b", "1")]


def test_cli_kappa(setup, capsys, tmp_path):
    cfg, _ = setup
    left = tmp_path / "left.csv"
    left.write_text(
        "case_id,verdict,note,first_upstream,modes,annotator\nr0001,pass,,,,a\nr0002,fail,x,,fabricated-evidence,a\nr0003,fail,y,,ignored-tool-output,a\n"
    )
    assert cli_main(["kappa", str(left), str(cfg.compare["other"])]) == 0
    out = capsys.readouterr().out
    assert "3 common cases" in out and "kappa 0.40" in out
