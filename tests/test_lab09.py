"""Module 9 lab: the simulated week, monitoring, sampling, the online judge, and closing the loop."""

import json
import math
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from annotate.app import Config, create_app
from evalkit.annotate import kappa_report, load_annotations, load_modes
from mediadoctor import lab09


def test_week_shape():
    reqs = lab09.traffic()
    assert len(reqs) == 766 and len({r.user for r in reqs}) == 176
    assert [r.ts for r in reqs] == sorted(r.ts for r in reqs)
    assert (
        reqs[0].ts.date().isoformat() == "2026-11-16"
        and reqs[-1].ts.date().isoformat() == "2026-11-22"
    )
    first42 = next(r for r in reqs if r.app_version == "4.2.0")
    assert first42.ts >= lab09.ROLLOUT
    assert {r.model for r in reqs if r.ts < lab09.SNAPSHOT_CHANGE} == {"claude-sonnet-5-5-20261001"}
    assert {r.model for r in reqs if r.ts >= lab09.SNAPSHOT_CHANGE} == {
        "claude-sonnet-5-5-20261116"
    }
    assert all(r.source.startswith("m9p") for r in reqs if r.source.startswith("m9")) and all(
        r.app_version == "4.2.0" for r in reqs if r.source.startswith("m9p")
    )  # only 4.2 users ask the drift questions
    retries = [r for r in reqs if r.retry_of]
    assert retries and all(lab09.by_id()[r.retry_of].source == r.source for r in retries)


def test_sources_and_labels():
    src = lab09.source_traces()
    assert len(src) == 140
    drift = load_annotations(lab09.reference_path())
    assert len(drift) == 40 and sum(a.failed for a in drift) == 1
    assert all(c["source"] == "synthetic-authored" for c in lab09.drift_cases())
    v2 = load_modes(lab09.modes_path("v2"))
    v1 = load_modes(lab09.modes_path("v1"))
    assert set(v2) - set(v1) == {"unknown-device-guess"}
    # the regenerated agent admits it has no vela-v2 profile: the v2 mode exists, but no reference
    # trace has it; the only failures are four traces with fabricated evidence
    used = {m for a in lab09.truth().values() for m in a.modes}
    assert used == {"fabricated-evidence"} and used <= set(v2)
    assert sorted(k for k, a in lab09.truth().items() if a.failed) == [
        "m3t010",
        "m3t072",
        "m3t088",
        "m9p27",
    ]
    fails = sum(lab09.label_of(r.id).failed for r in lab09.traffic())
    assert fails == 25 and fails / len(lab09.traffic()) == pytest.approx(0.033, abs=0.001)


def test_store_restamps_and_hides_nothing_it_should_keep():
    st = lab09.store()
    assert len(st) == 766 and sum(len(t) for t in st.values()) == 4635
    r = lab09.traffic()[100]
    t = st[r.id]
    root = lab09.root_of(t)
    assert root["trace_id"] == lab09.trace_id_of(r.id) and all(
        s["trace_id"] == root["trace_id"] for s in t
    )
    assert root["attributes"]["mediadoctor.case.id"] == r.id
    assert root["attributes"]["mediadoctor.app.version"] == r.app_version
    assert root["duration_ms"] == pytest.approx(r.latency_ms, rel=1e-3)
    assert root["start_time_unix_nano"] == int(r.ts.timestamp() * 1e9)
    assert {
        s["attributes"]["gen_ai.response.model"] for s in t if s["name"].startswith("chat")
    } == {r.model}
    # the source trace itself is untouched
    assert (
        lab09.root_of(lab09.source_traces()[r.source])["attributes"]["mediadoctor.case.id"]
        == r.source
    )


def test_tagger_is_perfect_on_its_own_questions_only():
    assert lab09.tagger_accuracy()[0] == 1.0
    acc, n, misses = lab09.tagger_accuracy(golden=True)
    assert n == 200 and acc == pytest.approx(0.845, abs=0.001)
    assert lab09.tag_topic("why does av1_2160p60.mkv stutter") == "av1-playback"
    assert lab09.tag_device("the vela-v2 drops frames") == "vela-v2"
    assert lab09.tag_device("no device here") == "(none)"


def test_daily_monitoring_numbers():
    rows = {r.date: r for r in lab09.daily()}
    assert [r.n for r in rows.values()] == [120, 125, 124, 131, 125, 75, 66]
    assert all(r.topic_psi < 0.1 for d, r in rows.items() if d < "2026-11-19")
    assert rows["2026-11-19"].topic_psi == pytest.approx(0.141, abs=0.001)
    assert all(r.topic_psi > 1 for d, r in rows.items() if d > "2026-11-19")
    assert rows["2026-11-19"].new_devices == ["vela-v2"]
    assert all(not r.new_devices for d, r in rows.items() if d < "2026-11-19")
    # tool errors appear with the rollout; the evidence check never fails all week
    assert rows["2026-11-20"].counts["tool_error"] == 37 and rows["2026-11-20"].rates[
        "tool_error"
    ] == pytest.approx(37 / 125)
    assert all(r.counts["tool_error"] == 0 for d, r in rows.items() if d < "2026-11-19")
    assert all(r.counts["evidence_fail"] == 0 for r in rows.values())
    p0, pts = lab09.chart("tool_error")
    assert p0 == 0.0
    assert [p.status for p in pts] == ["ok", "ok", "ok", "high", "high", "high", "high"]
    p0, pts = lab09.chart("evidence_fail")
    assert p0 == 0.0 and all(p.status == "ok" and p.rate == 0 for p in pts)
    assert lab09.slow_ms() == pytest.approx(22581.6, abs=0.1)


def test_cusum_alarms_and_version_change():
    te = lab09.cusum_alarm("tool_error")
    assert te.at is not None and te.hours_after_rollout == 8.6
    assert te.p0 == 0.005  # no tool errors in the reference window: p0 is floored
    assert te.when == datetime.fromisoformat("2026-11-19T18:36:20+05:30")
    assert lab09.cusum_alarm("evidence_fail").at is None  # the evidence check never fails
    assert lab09.cusum_alarm("thumbs_down").at is None  # feedback is too sparse to alarm
    (vc,) = lab09.version_changes()
    assert vc.old.endswith("20261001") and vc.new.endswith("20261116")
    assert vc.before == (0, 123) and vc.after == (0, 115) and vc.p == 1.0
    assert lab09.segments("tool_error") == {"4.1.3": (0, 111), "4.2.0": (90, 252)}
    assert lab09.segments("evidence_fail") == {"4.1.3": (0, 111), "4.2.0": (0, 252)}


def test_signal_quality():
    q = {s.signal: s for s in lab09.signal_quality()}
    # the one code check that fires (format) flags a trace the reference passes
    assert q["check_failed"].fired == 8 and q["check_failed"].precision == 0.0
    assert q["thumbs_down"].precision == pytest.approx(0.21, abs=0.01) and q[
        "thumbs_down"
    ].recall == pytest.approx(0.12, abs=0.01)
    # the agent handles the vela-v2 tool errors correctly: 90 alarms, no failures behind them
    assert q["tool_error"].fired == 90 and q["tool_error"].precision == 0.0
    best = max(q.values(), key=lambda s: s.precision)
    assert best.signal == "retried" and best.recall == pytest.approx(0.28, abs=0.01)
    assert q["thumbs_up"].precision == 0.0 and q["copied"].precision < 0.05


def test_queue_is_deterministic_deduplicated_and_interleaved():
    q = lab09.queue(limit=None)
    assert q == lab09.queue(limit=None)
    assert len({it.fingerprint for it in q}) == len(q)
    first = lab09.queue(limit=12)
    trig = [any(r.startswith("signal:") for r in it.reasons) for it in first]
    assert trig[:3] == [True, True, False] and trig.count(False) == 4
    assert first[0].reasons[0] == "signal:check_failed"
    st = lab09.store()
    for it in first:  # duplicates really are identical traces
        assert all(lab09.fingerprint(st[d]) == it.fingerprint for d in it.duplicates)
    top40 = lab09.queue(limit=40)
    top40_fails = [it.request_id for it in top40 if lab09.label_of(it.request_id).failed]
    assert top40_fails == ["r0031", "r0201", "r0634"]
    assert all(lab09.label_of(k).modes == ["fabricated-evidence"] for k in top40_fails)
    # the whole queue (88 distinct traces) reaches all 4 failing traces of the week
    assert len(q) == 88
    assert {
        lab09.by_id()[it.request_id].source for it in q if lab09.label_of(it.request_id).failed
    } == {
        "m3t010",
        "m3t072",
        "m3t088",
        "m9p27",
    }


def test_queue_bias_and_weighting():
    b = lab09.queue_bias()
    assert b["week (truth)"] == pytest.approx(0.033, abs=0.001)
    assert b["queue, unweighted"] == pytest.approx(0.058, abs=0.001)
    assert b["queue, weighted by 1/p"] == pytest.approx(0.040, abs=0.001)
    assert b["random part only"] == pytest.approx(0.069, abs=0.001)
    assert b["queue size"] == 207 and b["random part size"] == 29
    # weighting moves the queue's rate most of the way back to the truth
    assert abs(b["queue, weighted by 1/p"] - b["week (truth)"]) < abs(
        b["queue, unweighted"] - b["week (truth)"]
    )


def test_online_judge_without_failing_validation_traces_cannot_be_corrected():
    assert len(lab09.judged_sample()) == 230
    val = lab09.judge_validation()
    # module 5's test split has 28 traces, all passing: the judge's TNR is undefined
    assert len(val) == 28 and all(h and j for h, j in val)
    before, after = lab09.judge_estimates()
    assert (before.n, after.n) == (133, 94)
    # the judge passes everything on both sides of the rollout, and so does the truth
    assert before.observed == after.observed == 1.0
    assert before.truth == after.truth == 1.0
    # with no failing validation trace there is no correction and no interval to report
    assert all(math.isnan(x) for e in (before, after) for x in (e.corrected, e.low, e.high))
    assert lab09.judge_on_new_traffic() == (39, 0, 0, 0)  # no failing AV1 trace to test TNR on


def test_annotators_and_score():
    a = load_annotations(lab09.annotator_path("a"))
    b = load_annotations(lab09.annotator_path("b"))
    top40 = {it.request_id for it in lab09.queue(limit=40)}
    assert [x.case_id for x in a] == sorted(top40) and [x.case_id for x in b] == sorted(top40)
    rep = kappa_report(a, b)
    assert rep.observed == 1.0 and rep.kappa == pytest.approx(1.0)
    assert rep.per_mode == {"fabricated-evidence": (pytest.approx(1.0), 1, 0, 0)}
    # the annotators agree with each other, but both pass two traces the reference fails
    for labels in (a, b):
        s = lab09.score(labels)
        assert s["n"] == 40 and s["agree"] == 38
        assert s["report"].disagreements == ["r0031", "r0634"]
        assert s["kappa"] == pytest.approx(0.48, abs=0.01)


def test_close_loop():
    (cand,) = lab09.close_loop(load_annotations(lab09.annotator_path("a")))
    assert cand.request_ids == ["r0201"] and cand.modes == ["fabricated-evidence"]
    assert cand.proposed_split == "dev" and not cand.near_duplicate_of
    # every failing request of the week (reference labels): one candidate per distinct question
    week = lab09.close_loop([lab09.label_of(r.id) for r in lab09.traffic()])
    assert len(week) == 4 and sum(len(c.request_ids) for c in week) == 25
    assert sorted(c.proposed_split for c in week) == ["dev", "test", "test", "test"]
    assert all(c.proposed_split == lab09.proposed_split(c.id) for c in week)
    assert not any(c.near_duplicate_of for c in week)
    flagged = lab09.close_loop([load_annotations(lab09.annotator_path("a"))[2]], flagged=[])
    assert flagged == [] or flagged[0].verdict == "fail"


def test_dashboard_json_and_app_on_the_week(tmp_path):
    d = lab09.dashboard()
    assert len(d["days"]) == 7 and len(d["chart"]["points"]) == 7 and len(d["judge"]) == 2
    assert d["alarms"][1]["metric"] == "tool_error" and d["alarms"][1]["hours_after_rollout"] == 8.6
    traces = lab09.write_store(tmp_path / "traces.jsonl")
    queue = lab09.write_queue(lab09.queue(limit=10), tmp_path / "queue.jsonl")
    board = tmp_path / "board.json"
    board.write_text(json.dumps(d, default=str))
    cfg = Config(
        traces,
        lab09.modes_path("v1"),
        tmp_path / "labels",
        queue,
        board,
        {"b": lab09.annotator_path("b")},
    )
    c = TestClient(create_app(cfg))
    c.cookies.set("annotator", "me")
    r = c.get("/review/0")
    assert r.status_code == 200 and "mediadoctor.sim" not in r.text
    assert c.get("/dashboard").status_code == 200
    r = c.post(
        "/label/0", data={"verdict": "fail", "new_mode": "unknown-device-guess", "note": "n"}
    )
    assert r.status_code == 200
    assert (tmp_path / "labels" / "labels-me.csv").exists()


def test_cli(capsys):
    assert lab09.main(["monitor"]) == 0
    out = capsys.readouterr().out
    assert "Thu 19 18:36 IST (+8.6 h from the rollout)" in out and "4.2.0" in out
    assert (
        lab09.main(["agreement", str(lab09.annotator_path("a")), str(lab09.annotator_path("b"))])
        == 0
    )
    assert "Cohen's kappa 1.00" in capsys.readouterr().out
    assert lab09.main(["signals"]) == 0 and "precision" in capsys.readouterr().out
    assert lab09.main(["judge"]) == 0 and "TPR 1.00 (39/39)" in capsys.readouterr().out
    assert lab09.main(["tagger"]) == 0 and "0.845" in capsys.readouterr().out
