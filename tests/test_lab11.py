"""Module 11: cache-aware prices, percentiles, the experiment runner, metrics, and the reports."""

import csv
import math
import xml.etree.ElementTree as ET

import pytest

from evalkit import load_prices
from evalkit.config import Price
from evalkit.fixtures import canonical_json
from evalkit.golden import HoldoutAccessError, HoldoutGuard
from evalkit.stats import percentile
from mediadoctor import experiments as X
from mediadoctor import lab04, lab11

# --- evalkit additions ---------------------------------------------------------------------------------


def test_cache_prices_match_the_pricing_page_multipliers():
    prices = load_prices()
    for model, (inp, write, read) in {
        "claude-sonnet-5-5": (2.0, 2.50, 0.10),
        "claude-haiku-5-5": (0.10, 0.125, 0.01),
    }.items():
        p = prices[model]
        assert (p.input_per_mtok, p.cache_write, p.cache_read) == (inp, write, read)
        assert p.cache_write == pytest.approx(1.25 * p.input_per_mtok)


def test_cost_usd_counts_cache_tokens_and_batch_discount():
    p = Price(2.0, 10.0, 2.5, 0.1)
    assert p.cost_usd(1000, 100, 2000, 3000) == pytest.approx(0.0083)
    assert p.cost_usd(1000, 100, 2000, 3000, batch=True) == pytest.approx(0.00415)
    assert p.cost_usd(1000, 100) == pytest.approx(0.003)
    d = Price(1.0, 5.0)  # no cache prices given: the standard multipliers
    assert (d.cache_write, d.cache_read) == (1.25, pytest.approx(0.1))


def test_percentile_interpolates_like_numpy():
    xs = list(range(1, 101))
    assert percentile(xs, 0.5) == pytest.approx(50.5)
    assert percentile(xs, 0.95) == pytest.approx(95.05)
    assert percentile([3.0], 0.95) == 3.0
    assert percentile([5, 1, 3], 0.0) == 1 and percentile([5, 1, 3], 1.0) == 5


# --- experiments ---------------------------------------------------------------------------------------


def test_variants_change_one_thing_from_their_parent():
    vs = X.variants()
    assert list(vs) == ["v1", "v2", "v3", "v3-cache", "haiku", "cascade", "retry"]
    fields = ("prompt", "model", "cache", "strategy")
    for v in vs.values():
        if not v.parent:
            continue
        p = vs[v.parent]
        changed = [f for f in fields if getattr(v, f) != getattr(p, f)]
        assert len(changed) == 1 or (v.strategy != "single" and changed == ["model", "strategy"]), v
    assert (
        vs["cascade"].escalate_to == "claude-sonnet-5-5" and vs["retry"].judge == "claude-haiku-5-5"
    )


def test_cached_request_marks_the_prefix_and_it_is_long_enough_to_cache():
    req = X.build_request("claude-sonnet-5-5", "v3", True, [{"role": "user", "content": "hi"}])
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["tools"] is X.TOOLS
    prefix = len(canonical_json({"system": req["system"], "tools": req["tools"]})) // 4
    assert prefix >= 512  # the minimum cacheable prompt for Sonnet 5.5 and Haiku 5.5
    assert isinstance(X.build_request("claude-sonnet-5-5", "v1", False, [])["system"], str)


def test_few_shot_examples_do_not_leak_eval_questions():
    questions = [c["question"] for c in lab04.load_dataset()]
    assert not any(q in X.SYSTEM_AGENT_V3 for q in questions)
    assert X.FEW_SHOT_SOURCES == ("m3t059", "m3t065")


def test_parse_self_check():
    assert X.parse_self_check("CRITIQUE: none\nVERDICT: PASS") == (True, "none")
    assert X.parse_self_check("CRITIQUE: cites ffprobe\nVERDICT: FAIL") == (False, "cites ffprobe")
    with pytest.raises(ValueError):
        X.parse_self_check("looks fine")


def test_call_usage_prices_cache_reads():
    u = X.call_usage("claude-sonnet-5-5", {"input_tokens": 400, "output_tokens": 100,
                                           "cache_read_input_tokens": 1000})  # fmt: skip
    assert (u.calls, u.cache_read_tokens) == (1, 1000)
    assert u.cost_usd == pytest.approx((400 * 2 + 100 * 10 + 1000 * 0.1) / 1e6)


def test_reference_grader_agrees_with_the_labels():
    labels = lab11.reference_labels()
    assert len(labels) == 7 * 137
    for name in X.variants():
        for row in lab11.run_rows(name):
            mode = labels[(name, row.case_id)]
            assert row.graded == (mode == "none"), (name, row.case_id, mode, row.checks)
            checks = dict(row.checks)
            if mode in ("premise", "ignored"):
                assert not checks["correct"] and checks["citations"]
            if mode == "skipped":
                assert not checks["investigated"] or not checks["citations"]
            if mode == "format":
                assert not checks["format"]


def test_caching_changes_cost_and_latency_not_answers():
    a, b = lab11.task_results("v3"), lab11.task_results("v3-cache")
    assert [t.answer for t in a] == [t.answer for t in b]
    assert sum(t.usage.cost_usd for t in b) < 0.5 * sum(t.usage.cost_usd for t in a)
    first = b[0].attempts[0].usage
    assert first.cache_read_tokens + first.cache_write_tokens > 0
    assert sum(t.usage.cache_write_tokens > 0 for t in b) <= 1  # only the very first call writes


def test_cascade_and_retry_add_up_their_attempts():
    for t in lab11.task_results("cascade"):
        assert len(t.attempts) == (
            1
            if X.code_checks_pass(
                t.attempts[0].spans,
                {"expected_tools": []} | next(c for c in X.cases() if c["id"] == t.case_id),
            )
            else 2
        )  # noqa: E501
        assert t.latency_ms == pytest.approx(sum(a.latency_ms for a in t.attempts))
        if t.escalated:
            assert t.models == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    retried = [t for t in lab11.task_results("retry") if t.retried]
    assert retried and all(t.attempts[0].self_check is False for t in retried)
    checked = [
        s
        for s in retried[0].attempts[0].spans
        if s["attributes"].get("mediadoctor.self_check") is True
    ]  # noqa: E501
    assert checked and checked[0]["attributes"]["gen_ai.request.model"] == "claude-haiku-5-5"


# --- lab11 metrics and reports ---------------------------------------------------------------------------


def test_dev_and_holdout_splits():
    dev, hold = lab11.split_cases("dev"), lab11.split_cases("holdout")
    assert (len(dev), len(hold)) == (108, 29)
    assert not {c["id"] for c in dev} & {c["id"] for c in hold}


def test_summary_numbers():
    s = lab11.summary("v1")
    assert (s.n, s.successes, s.timeouts) == (108, 72, 1)
    assert s.cost_per_success == pytest.approx(s.cost_per_task * s.n / s.successes)
    assert s.cps_low < s.cost_per_success < s.cps_high
    assert s.p50_ms < s.p95_ms and s.cache_hit_rate == 0
    assert lab11.summary("v3-cache").successes == 92 and lab11.summary("retry").successes == 97
    assert lab11.summary("v3-cache").cache_hit_rate > 0.7


def test_cost_per_success_with_no_successes_is_infinite():
    r = lab11.run_rows("v1")[0]
    failed = lab11.Row(**{**r.__dict__, "graded": False})
    assert math.isinf(lab11.cost_per_success([failed]))


def test_pareto_front_and_cheapest_within():
    pts = [lab11.summary(n) for n in X.variants()]
    assert [p.variant for p in lab11.pareto_front(pts)] == ["haiku", "cascade", "v3-cache", "retry"]
    assert lab11.cheapest_within(pts, 0.02).variant == "retry"
    assert lab11.cheapest_within(pts, 0.05).variant == "v3-cache"


def test_decision_follows_the_preregistered_rule():
    d = lab11.decide()
    assert d.kept == ["v1", "v2", "v3", "v3-cache", "retry"]
    assert d.chosen == d.best == "retry"
    assert d.verdicts["haiku"][0] == d.verdicts["cascade"][0] == "reject"
    assert "graded answers identical: yes" in d.verdicts["v3-cache"][1]


def test_report_log_and_memo():
    rep = lab11.report_text()
    assert "v3-cache  vs v3" in rep and "Pareto frontier" in rep and "Failure modes" in rep
    log = lab11.log_markdown()
    assert log.count("## E") == 6 and "**Decision:** keep" in log and "**Decision:** reject" in log
    memo = lab11.memo_markdown(today="2026-11-23")
    for section in ("## Decision requested", "## How sure we are", "## What we are not saying"):
        assert section in memo
    assert "**retry on judge FAIL**" in memo and "(-51%)" in memo
    assert "thinnest step is retry on judge FAIL" in memo and "p=0.06" in memo
    assert len(memo.splitlines()) < 60  # one page


def test_pareto_svg_is_well_formed():
    svg = lab11.pareto_svg()
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    assert len(root.findall(f"{ns}circle")) == 7 and root.find(f"{ns}polyline") is not None
    assert "log scale" in svg


def test_latency_breakdown_names_the_retry():
    text = lab11.latency_text("retry")
    assert "self-check" in text and "retried" in text


def test_ev_ranks_by_value():
    fv = lab11.fix_values()
    assert [f.mode for f in fv[:2]] == ["ignored-tool-output", "fabricated-evidence"]
    assert max(fv, key=lambda f: f.per_day).mode == "fabricated-evidence"
    assert fv[0].ci[0] < fv[1].rate < fv[0].ci[1]  # the top two are not separable at n=100


def test_holdout_is_guarded_and_logged(tmp_path):
    with pytest.raises(HoldoutAccessError):
        lab11.task_results("v1", "holdout")
    guard = lab11.holdout_guard()
    with pytest.raises(HoldoutAccessError):
        lab11.confirm_holdout("v3-cache", release=False, guard=guard, log_path=tmp_path / "h.csv")
    sa, sb, p = lab11.confirm_holdout("v3-cache", True, guard, tmp_path / "h.csv")
    assert sa.n == sb.n == 29 and guard.looks == 1
    rows = list(csv.DictReader((tmp_path / "h.csv").open()))
    assert rows[0]["variant"] == "v3-cache" and rows[0]["n"] == "29"
    with pytest.raises(HoldoutAccessError):
        lab11.trace_text("v1", lab11.split_cases("holdout")[0]["id"])


def test_cli(capsys, tmp_path):
    assert lab11.main(["pareto", "--svg", str(tmp_path / "p.svg")]) == 0
    assert (tmp_path / "p.svg").read_text().startswith("<svg")
    assert lab11.main(["confirm", "v3-cache"]) == 2
    assert "refused" in capsys.readouterr().out
    assert lab11.main(["trace", "v3-cache", "m4q001"]) == 0
    assert "invoke_agent" in capsys.readouterr().out
    assert lab11.main(["cost", "--runs", "3"]) == 0
    assert "batch" in capsys.readouterr().out


def test_guard_type_is_evalkits():
    assert isinstance(lab11.holdout_guard(), HoldoutGuard)


def test_selfcheck_confusion():
    sc = lab11.selfcheck_stats()
    assert sc.tp + sc.fn + sc.tn + sc.fp == 108 and sc.retried == sc.tp + sc.fp
    assert sc.fixed <= sc.retried


def test_docs_frontier_chart_is_current():
    from evalkit import repo_root

    svg = repo_root() / "docs" / "modules" / "11-improving-with-evidence" / "pareto.svg"
    assert svg.read_text(encoding="utf-8") == lab11.pareto_svg()
