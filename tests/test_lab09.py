"""Module 9 lab: the simulated week, monitoring, sampling, the online judge, and closing the loop."""

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from annotate.app import Config, create_app
from evalkit.annotate import kappa_report, load_annotations, load_modes
from mediadoctor import lab09


def test_week_shape():
    reqs = lab09.traffic()
    assert len(reqs) == 776 and len({r.user for r in reqs}) == 176
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
    assert len(drift) == 40 and sum(a.failed for a in drift) == 22
    assert all(c["source"] == "synthetic-authored" for c in lab09.drift_cases())
    v2 = load_modes(lab09.modes_path("v2"))
    v1 = load_modes(lab09.modes_path("v1"))
    assert set(v2) - set(v1) == {"unknown-device-guess"}
    used = {m for a in lab09.truth().values() for m in a.modes}
    assert used <= set(v2) and "unknown-device-guess" in used
    week_fail = sum(lab09.label_of(r.id).failed for r in lab09.traffic()) / len(lab09.traffic())
    assert week_fail == pytest.approx(0.340, abs=0.001)


def test_store_restamps_and_hides_nothing_it_should_keep():
    st = lab09.store()
    assert len(st) == 776 and sum(len(t) for t in st.values()) == 4684
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
    assert n == 182 and acc == pytest.approx(0.835, abs=0.001)
    assert lab09.tag_topic("why does av1_2160p60.mkv stutter") == "av1-playback"
    assert lab09.tag_device("the vela-v2 drops frames") == "vela-v2"
    assert lab09.tag_device("no device here") == "(none)"


def test_daily_monitoring_numbers():
    rows = {r.date: r for r in lab09.daily()}
    assert [r.n for r in rows.values()] == [121, 126, 125, 133, 131, 74, 66]
    assert all(r.topic_psi < 0.1 for d, r in rows.items() if d < "2026-11-19")
    assert rows["2026-11-19"].topic_psi == pytest.approx(0.114, abs=0.001)
    assert rows["2026-11-21"].topic_psi > 2
    assert rows["2026-11-19"].new_devices == ["vela-v2"]
    assert all(not r.new_devices for d, r in rows.items() if d < "2026-11-19")
    assert rows["2026-11-20"].rates["evidence_fail"] == pytest.approx(16 / 131)
    p0, pts = lab09.chart("evidence_fail")
    assert p0 == pytest.approx(5 / 372)
    assert [p.status for p in pts] == ["ok", "ok", "ok", "high", "high", "high", "high"]
    assert lab09.slow_ms() == pytest.approx(6355.0, abs=0.1)


def test_cusum_alarms_and_version_change():
    te = lab09.cusum_alarm("tool_error")
    assert te.at is not None and te.hours_after_rollout == 5.0
    assert te.when == datetime.fromisoformat("2026-11-19T14:57:35+05:30")
    ev = lab09.cusum_alarm("evidence_fail")
    assert ev.hours_after_rollout == 19.7
    assert lab09.cusum_alarm("thumbs_down").at is None  # feedback is too sparse to alarm
    (vc,) = lab09.version_changes()
    assert vc.old.endswith("20261001") and vc.new.endswith("20261116")
    assert vc.before == (1, 125) and vc.after == (3, 115) and vc.p > 0.2
    seg = lab09.segments("evidence_fail")
    assert seg["4.1.3"] == (0, 112) and seg["4.2.0"] == (41, 255)


def test_signal_quality():
    q = {s.signal: s for s in lab09.signal_quality()}
    assert q["check_failed"].precision == 1.0
    assert (
        q["thumbs_down"].precision == pytest.approx(0.71, abs=0.01)
        and q["thumbs_down"].recall < 0.1
    )
    assert q["tool_error"].recall == pytest.approx(0.34, abs=0.01)
    assert q["thumbs_up"].precision < 0.2 and q["copied"].precision < 0.35


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
    assert sum("unknown-device-guess" in lab09.label_of(it.request_id).modes for it in top40) == 9


def test_queue_bias_and_weighting():
    b = lab09.queue_bias()
    assert b["week (truth)"] == pytest.approx(0.340, abs=0.001)
    assert b["queue, unweighted"] == pytest.approx(0.553, abs=0.001)
    assert b["queue, weighted by 1/p"] == pytest.approx(0.364, abs=0.001)
    assert b["queue size"] == 275


def test_online_judge_with_correction():
    assert len(lab09.judged_sample()) == 232
    assert len(lab09.judge_validation()) == 25
    before, after = lab09.judge_estimates()
    assert (before.n, after.n) == (132, 97)
    assert before.observed == pytest.approx(0.864, abs=0.001) and after.observed == pytest.approx(
        0.680, abs=0.001
    )
    assert before.truth == pytest.approx(0.932, abs=0.001) and after.truth == pytest.approx(
        0.784, abs=0.001
    )
    assert before.low <= before.truth <= before.high and after.low <= after.truth <= after.high
    assert after.high - after.low > 0.5  # 25 labelled traces cannot pin the judge's TNR down
    assert lab09.judge_on_new_traffic() == (27, 7, 0, 6)


def test_annotators_and_score():
    a = load_annotations(lab09.annotator_path("a"))
    b = load_annotations(lab09.annotator_path("b"))
    assert [x.case_id for x in a] == [it.request_id for it in lab09.queue(limit=40)]
    rep = kappa_report(a, b)
    assert rep.observed == 0.95 and rep.kappa == pytest.approx(0.875)
    assert rep.per_mode["vague-next-step"][0] == pytest.approx(0.48, abs=0.01)
    s = lab09.score(a)
    assert s["n"] == 40 and s["agree"] == 40  # A's differences are in the modes, not the verdicts


def test_close_loop():
    cands = lab09.close_loop(load_annotations(lab09.annotator_path("a")))
    assert len(cands) == 28 and len({c.question for c in cands}) == 28
    assert sum("unknown-device-guess" in c.modes for c in cands) == 9
    assert {c.proposed_split for c in cands} == {"train", "dev", "test"}
    assert all(c.proposed_split == lab09.proposed_split(c.id) for c in cands)
    assert sum(bool(c.near_duplicate_of) for c in cands) == 2
    flagged = lab09.close_loop([load_annotations(lab09.annotator_path("a"))[2]], flagged=[])
    assert flagged == [] or flagged[0].verdict == "fail"


def test_dashboard_json_and_app_on_the_week(tmp_path):
    d = lab09.dashboard()
    assert len(d["days"]) == 7 and len(d["chart"]["points"]) == 7 and len(d["judge"]) == 2
    assert d["alarms"][1]["metric"] == "tool_error" and d["alarms"][1]["hours_after_rollout"] == 5.0
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
    assert "Thu 19 14:57 IST (+5.0 h from the rollout)" in out and "4.2.0" in out
    assert (
        lab09.main(["agreement", str(lab09.annotator_path("a")), str(lab09.annotator_path("b"))])
        == 0
    )
    assert "Cohen's kappa 0.87" in capsys.readouterr().out
    assert lab09.main(["signals"]) == 0 and "precision" in capsys.readouterr().out
    assert lab09.main(["judge"]) == 0 and "TPR 0.79 (27/34)" in capsys.readouterr().out
    assert lab09.main(["tagger"]) == 0 and "0.835" in capsys.readouterr().out
