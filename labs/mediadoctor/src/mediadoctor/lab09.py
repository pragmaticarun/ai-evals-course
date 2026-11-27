"""Module 9 lab: production monitoring for MediaDoctor, and the review queue for the annotation app.

    uv run mediadoctor-lab09 simulate                 # the week's trace store -> runs/m9/traces.jsonl
    uv run mediadoctor-lab09 monitor [--json FILE]    # daily metrics, drift, control chart, CUSUM
    uv run mediadoctor-lab09 sample [--limit 60]      # review queue -> runs/m9/queue.jsonl
    uv run mediadoctor-lab09 signals                  # how well each user signal points at failures
    uv run mediadoctor-lab09 judge                    # online judge on a sample, judge-error corrected
    uv run mediadoctor-lab09 annotate                 # simulate + sample, then start the app
    uv run mediadoctor-lab09 agreement A.csv B.csv    # Cohen's kappa between two annotators
    uv run mediadoctor-lab09 score LABELS.csv         # your labels against the reference
    uv run mediadoctor-lab09 close-loop LABELS.csv    # golden-dataset candidates from your labels

The simulated week (Monday 16 to Sunday 22 November 2026, IST) is synthetic-authored: see
scripts/author_module09_fixtures.py. Each request replays one recorded trace: module 3's 100
traces (prompt v1, the release) before the drift, plus 40 AV1 traces recorded for this module.
What changes per request is the request id, user, time, app version, model snapshot, latency, and
the feedback. Two events are planted:

    Tue 17 Nov 14:00   the provider's model snapshot changes (no effect on quality)
    Thu 19 Nov 10:00   app 4.2 starts a staged rollout that makes AV1 the default codec; its users
                       ask about AV1, including on the new vela-v2 phone that MediaDoctor has no
                       device profile for

Everything replays from fixtures and needs no API key.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import LLM, Tracer, repo_root, text_of
from evalkit.annotate import (
    Annotation,
    FailureMode,
    kappa_report,
    load_annotations,
    load_modes,
)
from evalkit.judge import build_judge_request, parse_verdict
from evalkit.monitor import (
    Pick,
    bernoulli_cusum,
    build_queue,
    new_categories,
    p_chart,
    proportions,
    psi,
    stable_fraction,
    two_proportion_z,
    weighted_rate,
    weighted_rate_ci,
)
from evalkit.stats import bootstrap_corrected, wilson_interval
from evalkit.synth import jaccard, shingles
from evalkit.trace import VIRTUAL_EPOCH_NS, SeededIds, VirtualClock
from evalkit.viewer import root_of
from mediadoctor import lab03, lab05
from mediadoctor.lab01 import has_format
from mediadoctor.lab02 import STEP_BUDGET, check_evidence_is_real
from mediadoctor.toolagent import run_agent

PROD_NAMESPACE = "mediadoctor-m9-prod"
JUDGE_NAMESPACE = "mediadoctor-m9-judges"
JUDGE_NAMESPACES = (JUDGE_NAMESPACE, lab05.JUDGE_NAMESPACE)
ONLINE_JUDGE = "tool-grounding"
IST = timezone(timedelta(hours=5, minutes=30))
WEEK_START = datetime(2026, 11, 16, tzinfo=IST)
DAYS = 7
ROLLOUT = datetime(2026, 11, 19, 10, 0, tzinfo=IST)  # app 4.2: AV1 by default
SNAPSHOT_CHANGE = datetime(2026, 11, 17, 14, 0, tzinfo=IST)
REFERENCE_END = datetime(2026, 11, 19, 0, 0, tzinfo=IST)  # Mon to Wed: before anything moved
JUDGE_RATE = 0.3  # share of traffic the online judge sees (random, hash-based)
SIGNAL_ORDER = ("check_failed", "thumbs_down", "tool_error", "retried", "slow")
Trace = list[dict[str, Any]]


# --- Paths --------------------------------------------------------------------------------------


def data_dir() -> Path:
    return repo_root() / "data" / "production"


def drift_cases_path() -> Path:
    return data_dir() / "drift_cases.jsonl"


def traffic_path() -> Path:
    return data_dir() / "traffic.jsonl"


def reference_path() -> Path:
    """Reference labels for the 40 AV1 traces recorded for this module (synthetic-authored)."""
    return repo_root() / "data" / "labels" / "module09_reference.csv"


def annotator_path(who: str) -> Path:
    return repo_root() / "data" / "labels" / f"module09_annotator_{who}.csv"


def modes_path(version: str = "v1") -> Path:
    return repo_root() / "data" / "labels" / f"production_modes_{version}.toml"


def runs_dir() -> Path:
    return repo_root() / "runs" / "m9"


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root()))
    except ValueError:
        return str(path)


# --- Source traces --------------------------------------------------------------------------------


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


@cache
def drift_cases() -> tuple[dict[str, Any], ...]:
    return tuple(_jsonl(drift_cases_path()))


def run_drift(llm: LLM | None = None) -> list[dict[str, Any]]:
    """Replay the 40 AV1 traces recorded for this module through the real agent loop."""
    llm = llm or LLM(namespace=PROD_NAMESPACE)
    spans: list[dict[str, Any]] = []
    for i, case in enumerate(drift_cases()):
        tracer = Tracer(
            clock=VirtualClock(VIRTUAL_EPOCH_NS + i * 60_000_000_000),
            ids=SeededIds(f"mediadoctor-lab09:{case['id']}"),
        )
        run_agent(case["question"], llm=llm, tracer=tracer, case_id=case["id"])
        spans.extend(tracer.span_dicts())
    return spans


@cache
def source_traces() -> dict[str, Trace]:
    """case id -> trace for every recorded trace the simulated traffic replays."""
    out = lab03.traces_by_case(lab03.run_cases())
    out.update(lab03.traces_by_case(run_drift()))
    return out


@cache
def source_cases() -> dict[str, dict[str, Any]]:
    out = {c["id"]: c for c in lab03.load_cases()}
    out.update({c["id"]: c for c in drift_cases()})
    return out


@cache
def truth() -> dict[str, Annotation]:
    """Reference label per source case (module 3's 100 plus this module's 40)."""
    out = {a.case_id: a for a in load_annotations(lab03.reference_labels_path())}
    out.update({a.case_id: a for a in load_annotations(reference_path())})
    return out


# --- Traffic ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Request:
    id: str
    ts: datetime
    user: str
    app_version: str
    model: str
    source: str  # the recorded trace this request replays (simulation bookkeeping, not a feature)
    latency_ms: float
    thumb: str | None  # "up", "down", or None
    copied: bool
    retry_of: str | None

    @property
    def day(self) -> str:
        return self.ts.strftime("%a %d")

    @property
    def date(self) -> str:
        return self.ts.date().isoformat()

    @property
    def after_rollout(self) -> bool:
        return self.ts >= ROLLOUT

    @property
    def reference(self) -> bool:
        return self.ts < REFERENCE_END


@cache
def traffic() -> tuple[Request, ...]:
    out = []
    for r in _jsonl(traffic_path()):
        out.append(
            Request(
                r["id"],
                datetime.fromisoformat(r["ts"]),
                r["user"],
                r["app_version"],
                r["model"],
                r["sim_source"],
                float(r["latency_ms"]),
                r["feedback"].get("thumb"),
                bool(r["feedback"].get("copied")),
                r.get("retry_of"),
            )
        )
    return tuple(out)


@cache
def by_id() -> dict[str, Request]:
    return {r.id: r for r in traffic()}


def label_of(request_id: str) -> Annotation:
    """The reference label of a request (that of the trace it replays), keyed by request id."""
    a = truth()[by_id()[request_id].source]
    return Annotation(request_id, a.verdict, a.note, a.first_upstream, list(a.modes), a.annotator)


# --- Trace store --------------------------------------------------------------------------------------


def trace_id_of(request_id: str) -> str:
    return hashlib.sha256(f"mediadoctor-m9:{request_id}".encode()).hexdigest()[:32]


def restamp(trace: Trace, req: Request) -> Trace:
    """The source trace as this request saw it: new trace id, start time, latency, and metadata."""
    root = root_of(trace)
    r0, r1 = root["start_time_unix_nano"], root["end_time_unix_nano"]
    t0 = int(req.ts.timestamp() * 1e9)
    scale = req.latency_ms * 1e6 / max(1, r1 - r0)
    tid = trace_id_of(req.id)
    out = []
    for s in trace:
        s = copy.deepcopy(s)
        s["trace_id"] = tid
        s["start_time_unix_nano"] = t0 + int((s["start_time_unix_nano"] - r0) * scale)
        s["end_time_unix_nano"] = t0 + int((s["end_time_unix_nano"] - r0) * scale)
        s["duration_ms"] = round((s["end_time_unix_nano"] - s["start_time_unix_nano"]) / 1e6, 3)
        for e in s["events"]:
            e["time_unix_nano"] = t0 + int((e["time_unix_nano"] - r0) * scale)
        a = s["attributes"]
        if a.get("gen_ai.operation.name") == "chat":
            a["gen_ai.response.model"] = req.model
        if s["parent_span_id"] is None:
            a["mediadoctor.case.id"] = req.id
            a["mediadoctor.request.id"] = req.id
            a["mediadoctor.app.version"] = req.app_version
            a["user.id"] = req.user
            a["mediadoctor.sim.source_case"] = req.source
            if req.retry_of:
                a["mediadoctor.retry_of"] = req.retry_of
        s["resource"] = {**s["resource"], "service.version": req.app_version}
        out.append(s)
    return out


@cache
def store() -> dict[str, Trace]:
    """request id -> trace, for the whole week."""
    src = source_traces()
    return {r.id: restamp(src[r.source], r) for r in traffic()}


def write_store(path: Path | None = None) -> Path:
    path = path or runs_dir() / "traces.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for spans in store().values():
            for s in spans:
                fh.write(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n")
    return path


# --- Tagging (input drift) ----------------------------------------------------------------------------

TOPIC_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (topic, re.compile(rx, re.I))
    for topic, rx in (
        ("av1-playback", r"av1|av01"),
        ("drm-resolution", r"widevine|\bdrm\b|security level|capped at sd|\bSD\b|premium hd"),
        ("hdr-colour", r"\bhdr|washed|tone.?map|grey and flat|looks dull|hdr10"),
        ("codec-limits", r"codecexception|10-bit|main 10|configure|grid|thumbnail|decoder setup"),
        ("mp4-startup", r"faststart|moov|start(s|up)? (slowly|slow)|takes .* to start|progressive"),
        ("av-sync", r"lip.?sync|out of sync|offset|audio (is )?(ahead|behind|early|late)"),
        ("live-stream", r"\blive\b|behind.?live|resume"),
        (
            "audio-focus",
            r"audio focus|duck|navigation prompt|pauses? (when|for)|other app|phone calls?",
        ),
    )
)
DEVICE_RE = re.compile(r"\b([a-z]+-[a-z]\d)\b", re.I)
SCENARIO_TOPIC = {
    "av1-lumen": "av1-playback", "av1-atlas": "av1-playback", "av1-api": "av1-playback",
    "hdr-lumen": "hdr-colour", "hdr-atlas": "hdr-colour", "hdr-display-api": "hdr-colour",
    "latemoov": "mp4-startup", "faststart": "mp4-startup", "avoffset": "av-sync",
    "thumbs": "codec-limits", "main10": "codec-limits", "live": "live-stream",
    "audiofocus": "audio-focus", "widevine": "drm-resolution",
}  # fmt: skip


def tag_topic(question: str) -> str:
    """A cheap, rule-based topic tag: the first rule that matches, else "other"."""
    for topic, rx in TOPIC_RULES:
        if rx.search(question):
            return topic
    return "other"


def tag_device(question: str) -> str:
    m = DEVICE_RE.search(question)
    return m.group(1).lower() if m else "(none)"


def question_of(trace: Trace) -> str:
    return str(root_of(trace)["attributes"].get("mediadoctor.question", ""))


def answer_of(trace: Trace) -> str:
    return str(root_of(trace)["attributes"].get("mediadoctor.answer", ""))


def true_topic(case_id: str) -> str:
    c = source_cases()[case_id]
    return c.get("topic") or SCENARIO_TOPIC[c["scenario"]]


def tagger_accuracy(golden: bool = False) -> tuple[float, int, list[tuple[str, str, str]]]:
    """Accuracy of `tag_topic`, with the misses. By default on the week's own questions (which the
    rules were written against, so expect it to look perfect); with golden=True on module 4's
    dataset questions, which the rules never saw: the honest number."""
    if golden:
        from mediadoctor import lab04

        known = {r["id"]: (r["question"], r["topic"]) for r in lab04.load_dataset()}
    else:
        known = {cid: (c["question"], true_topic(cid)) for cid, c in source_cases().items()}
    misses = [(k, want, tag_topic(q)) for k, (q, want) in known.items() if tag_topic(q) != want]
    return 1 - len(misses) / len(known), len(known), misses


# --- Code checks on all traffic --------------------------------------------------------------------------


def tool_errors(trace: Trace) -> int:
    return sum(
        1
        for s in trace
        if s["attributes"].get("gen_ai.operation.name") == "execute_tool"
        and s["status"]["code"] == "ERROR"
    )


def model_calls(trace: Trace) -> int:
    return sum(1 for s in trace if s["attributes"].get("gen_ai.operation.name") == "chat")


CHECKS = {
    "format": lambda t: has_format({}, answer_of(t)),
    "evidence": check_evidence_is_real,  # every [tool:x] cited ran successfully
    "steps": lambda t: model_calls(t) <= STEP_BUDGET,
}


@cache
def check_results() -> dict[str, dict[str, bool]]:
    """request id -> {check: passed}. Cheap enough to run on every request."""
    by_source = {
        cid: {name: bool(fn(t)) for name, fn in CHECKS.items()}
        for cid, t in source_traces().items()
    }
    return {r.id: by_source[r.source] for r in traffic()}


def fingerprint(trace: Trace) -> str:
    """Same question and same answer -> same fingerprint. Label one, and the label covers all."""
    return hashlib.sha256((question_of(trace) + "\x00" + answer_of(trace)).encode()).hexdigest()[
        :12
    ]


# --- Signals ---------------------------------------------------------------------------------------------


@cache
def slow_ms() -> float:
    """The latency signal's threshold: the 95th percentile of the reference window (Mon to Wed)."""
    lat = sorted(r.latency_ms for r in traffic() if r.reference)
    return lat[int(0.95 * (len(lat) - 1))]


@cache
def retried_ids() -> frozenset[str]:
    return frozenset(r.retry_of for r in traffic() if r.retry_of)


@cache
def signals() -> dict[str, tuple[str, ...]]:
    """request id -> the signals it raised. Explicit: thumbs_down. Implicit: retried (the user
    asked again within minutes). Operational: tool_error, slow. Code: check_failed."""
    out = {}
    checks = check_results()
    st = store()
    for r in traffic():
        sig = []
        if r.thumb == "down":
            sig.append("thumbs_down")
        if tool_errors(st[r.id]):
            sig.append("tool_error")
        if not all(checks[r.id].values()):
            sig.append("check_failed")
        if r.id in retried_ids():
            sig.append("retried")
        if r.latency_ms > slow_ms():
            sig.append("slow")
        out[r.id] = tuple(sig)
    return out


@dataclass(frozen=True)
class SignalQuality:
    signal: str
    fired: int
    precision: float  # of the requests it flags, the share that truly fail
    recall: float  # of the truly failing requests, the share it flags


def signal_quality() -> list[SignalQuality]:
    sig = signals()
    fails = {r.id for r in traffic() if label_of(r.id).failed}
    out = []
    for s in (*SIGNAL_ORDER, "thumbs_up", "copied"):
        if s == "thumbs_up":
            hit = {r.id for r in traffic() if r.thumb == "up"}
        elif s == "copied":
            hit = {r.id for r in traffic() if r.copied}
        else:
            hit = {k for k, v in sig.items() if s in v}
        tp = len(hit & fails)
        out.append(SignalQuality(s, len(hit), tp / len(hit) if hit else 0.0, tp / len(fails)))
    return out


# --- Monitoring ------------------------------------------------------------------------------------------

METRICS = ("evidence_fail", "tool_error", "format_fail", "thumbs_down", "retried", "slow")


def metric_values(r: Request) -> dict[str, bool]:
    c, s = check_results()[r.id], signals()[r.id]
    return {
        "evidence_fail": not c["evidence"],
        "tool_error": "tool_error" in s,
        "format_fail": not c["format"],
        "thumbs_down": r.thumb == "down",
        "retried": "retried" in s,
        "slow": "slow" in s,
    }


def days() -> list[str]:
    return [(WEEK_START + timedelta(days=i)).date().isoformat() for i in range(DAYS)]


def day_label(date: str) -> str:
    return datetime.fromisoformat(date).strftime("%a %d")


@dataclass
class DayRow:
    date: str
    n: int
    rates: dict[str, float]
    counts: dict[str, int]
    topic_psi: float
    new_devices: list[str]
    av1_share: float
    app42_share: float


def reference_requests() -> list[Request]:
    return [r for r in traffic() if r.reference]


def topics_of(reqs: Iterable[Request]) -> list[str]:
    st = store()
    return [tag_topic(question_of(st[r.id])) for r in reqs]


def devices_of(reqs: Iterable[Request]) -> list[str]:
    st = store()
    return [tag_device(question_of(st[r.id])) for r in reqs]


def daily() -> list[DayRow]:
    ref = reference_requests()
    ref_topics, ref_devices = topics_of(ref), devices_of(ref)
    rows = []
    for d in days():
        reqs = [r for r in traffic() if r.date == d]
        vals = [metric_values(r) for r in reqs]
        counts = {m: sum(v[m] for v in vals) for m in METRICS}
        topics = topics_of(reqs)
        rows.append(
            DayRow(
                d,
                len(reqs),
                {m: counts[m] / len(reqs) for m in METRICS},
                counts,
                psi(ref_topics, topics),
                new_categories(ref_devices, devices_of(reqs)),
                proportions(topics).get("av1-playback", 0.0),
                sum(r.app_version.startswith("4.2") for r in reqs) / len(reqs),
            )
        )
    return rows


def reference_rate(metric: str) -> float:
    ref = reference_requests()
    return sum(metric_values(r)[metric] for r in ref) / len(ref)


def chart(metric: str, bucket_hours: int = 24):
    """p-chart of a metric per bucket (default: per day) against the reference window's rate."""
    p0 = reference_rate(metric)
    periods = []
    start = WEEK_START
    while start < WEEK_START + timedelta(days=DAYS):
        end = start + timedelta(hours=bucket_hours)
        reqs = [r for r in traffic() if start <= r.ts < end]
        label = start.strftime("%a %d") + ("" if bucket_hours == 24 else start.strftime(" %H:%M"))
        periods.append((label, len(reqs), sum(metric_values(r)[metric] for r in reqs)))
        start = end
    return p0, p_chart(p0, periods)


@dataclass(frozen=True)
class Alarm:
    metric: str
    p0: float
    p1: float
    h: float
    at: str | None  # request id
    when: datetime | None
    hours_after_rollout: float | None


def cusum_alarm(metric: str, ratio: float = 2.0, h: float = 4.0) -> Alarm:
    """Bernoulli CUSUM over the request stream in time order, tuned to catch the metric's rate
    doubling (p1 = ratio x p0, the reference rate)."""
    p0 = max(reference_rate(metric), 0.005)
    p1 = min(0.95, ratio * p0)
    reqs = list(traffic())
    c = bernoulli_cusum([metric_values(r)[metric] for r in reqs], p0, p1, h)
    if c.alarm_at is None:
        return Alarm(metric, p0, p1, h, None, None, None)
    r = reqs[c.alarm_at]
    return Alarm(metric, p0, p1, h, r.id, r.ts, round((r.ts - ROLLOUT).total_seconds() / 3600, 1))


@dataclass(frozen=True)
class VersionChange:
    when: datetime
    old: str
    new: str
    metric: str
    before: tuple[int, int]
    after: tuple[int, int]
    diff: float
    p: float


def version_changes(metric: str = "evidence_fail", window_hours: int = 24) -> list[VersionChange]:
    """Every change of model snapshot, with the metric in the window before and after it."""
    out = []
    reqs = list(traffic())
    for prev, cur in zip(reqs, reqs[1:], strict=False):
        if cur.model == prev.model:
            continue
        w = timedelta(hours=window_hours)
        before = [r for r in reqs if cur.ts - w <= r.ts < cur.ts]
        after = [r for r in reqs if cur.ts <= r.ts < cur.ts + w]
        xb = sum(metric_values(r)[metric] for r in before)
        xa = sum(metric_values(r)[metric] for r in after)
        diff, _, p = two_proportion_z(xb, len(before), xa, len(after))
        out.append(
            VersionChange(
                cur.ts, prev.model, cur.model, metric, (xb, len(before)), (xa, len(after)), diff, p
            )
        )
    return out


def segments(metric: str, since: datetime = ROLLOUT) -> dict[str, tuple[int, int]]:
    """(failures, n) of a metric per app version, after `since`: where is the change coming from?"""
    out: dict[str, list[int]] = {}
    for r in traffic():
        if r.ts < since:
            continue
        x = out.setdefault(r.app_version, [0, 0])
        x[0] += metric_values(r)[metric]
        x[1] += 1
    return {k: (v[0], v[1]) for k, v in sorted(out.items())}


# --- Online judge on a sample, with judge-error correction --------------------------------------------------


def judge_llm() -> _JudgeChain:
    return _JudgeChain()


class _JudgeChain:
    """Replays the online judge from this module's fixtures, then module 5's."""

    def __init__(self) -> None:
        self.llms = [LLM(namespace=ns) for ns in JUDGE_NAMESPACES]

    def has(self, request: dict[str, Any]) -> bool:
        return any(llm.store.has(request) for llm in self.llms)

    def create(self, **request: Any) -> dict[str, Any]:
        for llm in self.llms:
            if llm.store.has(request):
                return llm.create(**request)
        return self.llms[-1].create(**request)  # raises FixtureMissingError with the key


@cache
def judge_verdicts() -> dict[str, bool | None]:
    """source case -> online judge PASS/FAIL (None where the judge does not apply)."""
    spec = lab05.load_spec(ONLINE_JUDGE)
    examples = lab05.items()
    llm = judge_llm()
    out: dict[str, bool | None] = {}
    for cid, t in source_traces().items():
        item = lab05.item_from_trace(t)
        if not lab05.applies(spec, item):
            out[cid] = None
            continue
        resp = llm.create(**build_judge_request(spec, item, examples))
        out[cid] = bool(parse_verdict(cid, text_of(resp)).passed)
    return out


def judged_sample() -> list[Request]:
    """The online judge's sample: JUDGE_RATE of all requests, picked by a hash of the request id."""
    return [r for r in traffic() if stable_fraction(r.id, "online-judge") < JUDGE_RATE]


@cache
def judge_validation() -> list[tuple[bool, bool]]:
    """(human pass, judge pass) for the online judge on module 5's test split: its TPR and TNR."""
    v = lab05.validate(ONLINE_JUDGE, None, "test")
    return [(v.human[c], bool(x.passed)) for c, x in v.verdicts.items()]


@dataclass(frozen=True)
class JudgeEstimate:
    period: str
    n: int
    observed: float
    corrected: float
    low: float
    high: float
    truth: float  # only a simulation can show this column


def criterion_pass(request_id: str) -> bool:
    """The human verdict for the online judge's criterion: no ignored-tool-output."""
    return lab05.load_spec(ONLINE_JUDGE).mode not in label_of(request_id).modes


def judge_estimates() -> list[JudgeEstimate]:
    verdicts = judge_verdicts()
    out = []
    for name, keep in (
        ("before rollout", lambda r: not r.after_rollout),
        ("after rollout", lambda r: r.after_rollout),
    ):
        reqs = [r for r in judged_sample() if keep(r) and verdicts[r.source] is not None]
        obs = [bool(verdicts[r.source]) for r in reqs]
        est = bootstrap_corrected(judge_validation(), obs, draws=2000, seed=9)
        tr = sum(criterion_pass(r.id) for r in reqs) / len(reqs)
        out.append(
            JudgeEstimate(name, len(reqs), est.observed, est.corrected, est.low, est.high, tr)
        )
    return out


def judge_on_new_traffic() -> tuple[int, int, int, int]:
    """(TP, FN, FP, TN) of the online judge on the AV1 traces recorded for this module, with
    "positive" = PASS as in module 5. Compare with its validation numbers: is it still as good?"""
    verdicts = judge_verdicts()
    mode = lab05.load_spec(ONLINE_JUDGE).mode
    tp = fn = fp = tn = 0
    for c in drift_cases():
        v = verdicts[c["id"]]
        if v is None:
            continue
        human = mode not in truth()[c["id"]].modes
        tp += human and v
        fn += human and not v
        fp += (not human) and v
        tn += (not human) and not v
    return tp, fn, fp, tn


# --- The review queue -------------------------------------------------------------------------------------


@dataclass
class QueueItem:
    request_id: str
    trace_id: str
    fingerprint: str
    reasons: list[str]
    prob: float
    duplicates: list[str] = field(default_factory=list)  # other requests with the same trace
    topic: str = ""
    day: str = ""
    judge: str = ""  # online judge verdict, when this request was in the judge's sample


def interleave(
    triggered: list[QueueItem], others: list[QueueItem], every: int = 3
) -> list[QueueItem]:
    """Every `every`-th item comes from the random/stratified part, so a reviewer never sees a long
    run of failures and starts expecting them."""
    out, t, o = [], list(triggered), list(others)
    while t or o:
        take_other = (len(out) + 1) % every == 0
        src = o if (take_other and o) or not t else t
        out.append(src.pop(0))
    return out


def queue(
    limit: int | None = 60, rate: float = 0.05, per_stratum: int = 3, dedupe: bool = True
) -> list[QueueItem]:
    """Signal-triggered picks interleaved with a random and a topic-stratified sample (two
    triggered, then one other). Requests that replay an identical trace are folded into one item
    (their ids are listed under duplicates)."""
    st = store()
    keys = [r.id for r in traffic()]
    strata = {k: tag_topic(question_of(st[k])) for k in keys}
    picks = build_queue(
        keys, signals(), strata, rate=rate, per_stratum=per_stratum, signal_order=SIGNAL_ORDER
    )
    judged = {r.id for r in judged_sample()}
    verdicts = judge_verdicts()
    fp_of = {k: fingerprint(st[k]) for k in keys}
    groups: dict[str, list[str]] = {}
    for k in keys:
        groups.setdefault(fp_of[k], []).append(k)
    items: list[QueueItem] = []
    seen: set[str] = set()
    for p in picks:
        fp = fp_of[p.key]
        if dedupe and fp in seen:
            continue
        seen.add(fp)
        r = by_id()[p.key]
        v = verdicts[r.source] if p.key in judged else None
        items.append(
            QueueItem(
                p.key,
                trace_id_of(p.key),
                fp,
                list(p.reasons),
                round(p.prob, 4),
                [k for k in groups[fp] if k != p.key] if dedupe else [],
                strata[p.key],
                r.day,
                "" if v is None else ("PASS" if v else "FAIL"),
            )
        )
    trig = [it for it in items if any(r.startswith("signal:") for r in it.reasons)]
    rest = [it for it in items if not any(r.startswith("signal:") for r in it.reasons)]
    items = interleave(trig, rest)
    return items[:limit] if limit else items


def picks_for_estimate(rate: float = 0.05, per_stratum: int = 3) -> list[Pick]:
    st = store()
    keys = [r.id for r in traffic()]
    strata = {k: tag_topic(question_of(st[k])) for k in keys}
    return build_queue(keys, signals(), strata, rate=rate, per_stratum=per_stratum)


def queue_bias() -> dict[str, float]:
    """True failure rate of the week vs what a review queue suggests, naive and weighted."""
    picks = picks_for_estimate()
    vals = {p.key: label_of(p.key).failed for p in picks}
    probs = {p.key: p.prob for p in picks}
    week = sum(label_of(r.id).failed for r in traffic()) / len(traffic())
    rnd = [p.key for p in picks if "random" in p.reasons]
    return {
        "week (truth)": week,
        "queue, unweighted": sum(vals.values()) / len(vals),
        "queue, weighted by 1/p": weighted_rate(vals, probs),
        "random part only": sum(label_of(k).failed for k in rnd) / len(rnd),
        "queue size": float(len(picks)),
        "random part size": float(len(rnd)),
    }


def queue_bias_intervals() -> dict[str, tuple[float, float]]:
    """95% intervals for queue_bias(): bootstrap for the weighted rate, Wilson for the random part."""
    picks = picks_for_estimate()
    vals = {p.key: label_of(p.key).failed for p in picks}
    probs = {p.key: p.prob for p in picks}
    rnd = [p.key for p in picks if "random" in p.reasons]
    k = sum(label_of(key).failed for key in rnd)
    return {
        "queue, weighted by 1/p": weighted_rate_ci(vals, probs),
        "random part only": wilson_interval(k, len(rnd)),
    }


def write_queue(items: Sequence[QueueItem], path: Path | None = None) -> Path:
    path = path or runs_dir() / "queue.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(asdict(it), sort_keys=True) + "\n")
    return path


# --- Labels: agreement, scoring, closing the loop -----------------------------------------------------------


def score(labels: Sequence[Annotation]) -> dict[str, Any]:
    """Your verdicts against the reference, by request id."""
    pairs = [(a, label_of(a.case_id)) for a in labels if a.case_id in by_id()]
    agree = sum(a.verdict == b.verdict for a, b in pairs)
    rep = kappa_report(list(labels), [b for _, b in pairs], "you", "reference")
    return {"n": len(pairs), "agree": agree, "kappa": rep.kappa, "report": rep}


def taxonomy_modes(version: str = "v2") -> dict[str, FailureMode]:
    return load_modes(modes_path(version))


def golden_texts() -> dict[str, str]:
    from mediadoctor import lab04

    return {r["id"]: r["question"] for r in lab04.load_dataset()}


@dataclass
class Candidate:
    id: str
    question: str
    verdict: str
    modes: list[str]
    note: str
    topic: str
    device: str
    request_ids: list[str]
    proposed_split: str
    near_duplicate_of: str
    similarity: float
    status: str = "proposed"
    source: str = "production 2026-11-16..22 (simulated)"


def proposed_split(key: str, test_share: float = 0.2, dev_share: float = 0.25) -> str:
    """A stable split for a new golden case: hash-based, so re-running never moves a case."""
    u = stable_fraction(key, "golden-split")
    return "test" if u < test_share else "dev" if u < test_share + dev_share else "train"


def close_loop(
    labels: Sequence[Annotation], flagged: Iterable[str] = (), threshold: float = 0.35
) -> list[Candidate]:
    """Golden-dataset candidates from reviewed production traces.

    Every failing trace and every trace flagged for the golden set becomes a candidate, once per
    distinct question. Each gets a stable proposed split and the most similar existing golden
    question, so near-duplicates are reviewed before they are added (and never land in a
    different split from their twin). Nothing is written into data/golden/ automatically.
    """
    st = store()
    flagged = set(flagged)
    gold = golden_texts()
    gold_sh = {k: shingles(v) for k, v in gold.items()}
    by_q: dict[str, Candidate] = {}
    for a in labels:
        if a.case_id not in st or not (a.failed or a.case_id in flagged):
            continue
        q = question_of(st[a.case_id])
        if q in by_q:
            by_q[q].request_ids.append(a.case_id)
            continue
        sh = shingles(q)
        best, sim = max(((k, jaccard(sh, v)) for k, v in gold_sh.items()), key=lambda t: t[1])
        cid = "m9c-" + hashlib.sha256(q.encode()).hexdigest()[:8]
        by_q[q] = Candidate(
            cid,
            q,
            a.verdict,
            list(a.modes),
            a.note,
            tag_topic(q),
            tag_device(q),
            [a.case_id],
            proposed_split(cid),
            best if sim >= threshold else "",
            round(sim, 3),
        )
    return list(by_q.values())


# --- Dashboard ---------------------------------------------------------------------------------------------


def dashboard() -> dict[str, Any]:
    """Everything the annotation app's dashboard page shows, as plain JSON."""
    rows = daily()
    alarms = [cusum_alarm(m) for m in ("evidence_fail", "tool_error", "thumbs_down")]
    _, pts = chart("evidence_fail")
    return {
        "title": "MediaDoctor production, Mon 16 to Sun 22 Nov 2026 (simulated)",
        "events": [
            {"when": SNAPSHOT_CHANGE.isoformat(), "what": "model snapshot change"},
            {"when": ROLLOUT.isoformat(), "what": "app 4.2 rollout starts (AV1 by default)"},
        ],
        "days": [
            {
                "date": r.date,
                "label": day_label(r.date),
                "n": r.n,
                "rates": {k: round(v, 4) for k, v in r.rates.items()},
                "topic_psi": round(r.topic_psi, 3),
                "av1_share": round(r.av1_share, 3),
                "new_devices": r.new_devices,
            }
            for r in rows
        ],
        "chart": {
            "metric": "evidence_fail",
            "points": [
                {
                    "label": p.label,
                    "rate": round(p.rate, 4),
                    "lcl": round(p.lcl, 4),
                    "ucl": round(p.ucl, 4),
                    "status": p.status,
                }
                for p in pts
            ],
        },
        "alarms": [
            {
                "metric": a.metric,
                "p0": round(a.p0, 4),
                "p1": round(a.p1, 4),
                "when": a.when.isoformat() if a.when else None,
                "hours_after_rollout": a.hours_after_rollout,
            }
            for a in alarms
        ],
        "judge": [asdict(e) for e in judge_estimates()],
    }


# --- Rendering and CLI ----------------------------------------------------------------------------------------


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def render_monitor() -> str:
    rows = daily()
    lines = [
        f"{len(traffic())} requests, {len({r.user for r in traffic()})} users; reference window "
        f"Mon 16 to Wed 18 ({len(reference_requests())} requests)",
        "",
        "day      n    evidence  tool_err  format  thumbs_dn  retried  slow   AV1   app4.2  topic PSI  new devices",
    ]
    for r in rows:
        x = r.rates
        lines.append(
            f"{day_label(r.date):7} {r.n:4}  {pct(x['evidence_fail']):>8}  {pct(x['tool_error']):>8}  "
            f"{pct(x['format_fail']):>6}  {pct(x['thumbs_down']):>9}  {pct(x['retried']):>7}  "
            f"{pct(x['slow']):>5}  {pct(r.av1_share):>5}  {pct(r.app42_share):>6}  {r.topic_psi:9.3f}  "
            f"{', '.join(r.new_devices) or '-'}"
        )
    p0, pts = chart("evidence_fail")
    lines += ["", f"p-chart, evidence_fail (reference rate {pct(p0)}, 3-sigma limits per day):"]
    for p in pts:
        lines.append(
            f"  {p.label}  n={p.n:3}  {pct(p.rate):>6}  limits [{pct(p.lcl)}, {pct(p.ucl)}]  {p.status}"
        )
    lines += ["", "CUSUM alarms (p1 = 2 x reference rate, h = 4):"]
    for m in ("evidence_fail", "tool_error", "thumbs_down", "format_fail"):
        a = cusum_alarm(m)
        when = (
            f"{a.when:%a %d %H:%M} IST ({a.hours_after_rollout:+.1f} h from the rollout)"
            if a.when
            else "no alarm"
        )
        lines.append(f"  {m:13} p0={pct(a.p0):>6} p1={pct(a.p1):>6}  {when}")
    lines += ["", "Model snapshot changes (evidence_fail, 24 h before vs after):"]
    for v in version_changes():
        lines.append(
            f"  {v.when:%a %d %H:%M} IST  {v.old} -> {v.new}: {v.before[0]}/{v.before[1]} -> "
            f"{v.after[0]}/{v.after[1]} ({v.diff:+.3f}, p={v.p:.2f})"
        )
    lines += ["", "After the rollout, by app version (evidence_fail, tool_error):"]
    ev, te = segments("evidence_fail"), segments("tool_error")
    for k in ev:
        lines.append(
            f"  {k:7} n={ev[k][1]:3}  evidence_fail {pct(ev[k][0] / ev[k][1]):>6}  "
            f"tool_error {pct(te[k][0] / te[k][1]):>6}"
        )
    return "\n".join(lines)


def _rate(k: int, n: int) -> str:
    """k/n to two decimals, or "n/a (0/0)" when there is nothing to estimate it from."""
    return f"{k / n:.2f}" if n else "n/a (0/0)"


def render_judge() -> str:
    tp, fn, fp, tn = judge_on_new_traffic()
    val = judge_validation()
    vtp = sum(h and j for h, j in val)
    vtn = sum((not h) and (not j) for h, j in val)
    vpos, vneg = sum(h for h, _ in val), sum(not h for h, _ in val)
    lines = [
        f"Online judge: {ONLINE_JUDGE} on a {int(JUDGE_RATE * 100)}% random sample "
        f"({len(judged_sample())} of {len(traffic())} requests; it applies where a tool succeeded).",
        f"Correction uses module 5's test split: TPR {_rate(vtp, vpos)}, TNR {_rate(vtn, vneg)} "
        f"(n={len(val)}).",
        "",
        "period            n   observed  corrected [95% CI]       truth (simulation only)",
    ]
    for e in judge_estimates():
        lines.append(
            f"{e.period:15} {e.n:4}   {e.observed:.3f}     {e.corrected:.3f} [{e.low:.3f}, {e.high:.3f}]   {e.truth:.3f}"
        )
    lines += [
        "",
        f"On the 40 new AV1 traces: TPR {tp / max(1, tp + fn):.2f} ({tp}/{tp + fn}), "
        f"TNR {tn / max(1, tn + fp):.2f} ({tn}/{tn + fp}).",
    ]
    return "\n".join(lines)


def render_signals() -> str:
    week = sum(label_of(r.id).failed for r in traffic()) / len(traffic())
    lines = [
        f"True failure rate of the week: {pct(week)} (reference labels, simulation only)",
        "",
        "signal         fired  precision  recall",
    ]
    for q in signal_quality():
        lines.append(f"{q.signal:13} {q.fired:6}  {q.precision:9.2f}  {q.recall:6.2f}")
    return "\n".join(lines)


def render_queue(items: Sequence[QueueItem]) -> str:
    st = store()
    lines = [f"{len(items)} items (identical traces folded together)", ""]
    for i, it in enumerate(items, 1):
        q = question_of(st[it.request_id])
        dup = f" +{len(it.duplicates)}" if it.duplicates else ""
        lines.append(
            f"{i:3}. {it.request_id}{dup:5} {it.day}  {','.join(it.reasons):34.34}  {q[:60]}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mediadoctor-lab09", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("simulate")
    sp.add_argument("--out", type=Path)
    sp = sub.add_parser("monitor")
    sp.add_argument("--json", type=Path)
    sp = sub.add_parser("sample")
    sp.add_argument("--limit", type=int, default=60)
    sp.add_argument("--rate", type=float, default=0.05)
    sp.add_argument("--per-stratum", type=int, default=3)
    sp.add_argument("--out", type=Path)
    sub.add_parser("signals")
    sub.add_parser("judge")
    sub.add_parser("tagger")
    sp = sub.add_parser("annotate")
    sp.add_argument("--port", type=int, default=8009)
    sp.add_argument("--limit", type=int, default=60)
    sp = sub.add_parser("agreement")
    sp.add_argument("left", type=Path)
    sp.add_argument("right", type=Path)
    sp = sub.add_parser("score")
    sp.add_argument("labels", type=Path)
    sp = sub.add_parser("close-loop")
    sp.add_argument("labels", type=Path)
    sp.add_argument("--flagged", type=Path, help="golden flags exported by the app (JSON list)")
    sp.add_argument("--out", type=Path)
    a = ap.parse_args(argv)

    if a.cmd == "simulate":
        path = write_store(a.out)
        print(
            f"wrote {rel(path)}: {len(traffic())} requests, {sum(len(t) for t in store().values())} spans"
        )
    elif a.cmd == "monitor":
        print(render_monitor())
        if a.json:
            a.json.parent.mkdir(parents=True, exist_ok=True)
            a.json.write_text(json.dumps(dashboard(), indent=2, default=str) + "\n")
            print(f"\nwrote {rel(a.json)}")
    elif a.cmd == "sample":
        items = queue(a.limit, a.rate, a.per_stratum)
        print(render_queue(items))
        path = write_queue(items, a.out)
        print(f"\nwrote {rel(path)}")
    elif a.cmd == "signals":
        print(render_signals())
    elif a.cmd == "judge":
        print(render_judge())
    elif a.cmd == "tagger":
        acc, n, _ = tagger_accuracy()
        print(
            f"tag_topic accuracy {acc:.3f} on the week's {n} distinct questions (rules written on them)"
        )
        acc, n, misses = tagger_accuracy(golden=True)
        print(
            f"tag_topic accuracy {acc:.3f} on {n} module 4 questions it never saw; misses by topic:"
        )
        for (want, got), k in Counter((w, g) for _, w, g in misses).most_common():
            print(f"  {want:15} -> {got:15} {k}")
    elif a.cmd == "annotate":
        from annotate.app import Config, serve

        traces = write_store()
        q = write_queue(queue(a.limit))
        board = runs_dir() / "dashboard.json"
        board.write_text(json.dumps(dashboard(), indent=2, default=str) + "\n")
        serve(
            Config(
                traces=traces,
                modes=modes_path("v1"),
                out_dir=runs_dir() / "labels",
                queue=q,
                dashboard=board,
                compare={"annotator-b": annotator_path("b")},
                title="MediaDoctor trace review",
            ),
            port=a.port,
        )
    elif a.cmd == "agreement":
        rep = kappa_report(
            load_annotations(a.left), load_annotations(a.right), short(a.left), short(a.right)
        )
        print(render_kappa(rep))
    elif a.cmd == "score":
        s = score(load_annotations(a.labels))
        print(f"{s['agree']}/{s['n']} verdicts agree with the reference; kappa {s['kappa']:.2f}")
        for cid in s["report"].disagreements:
            ref = label_of(cid)
            why = ", ".join(ref.modes) or "no failure mode"
            print(
                f"  {cid}: reference says {ref.verdict} ({why}){': ' + ref.note[:70] if ref.note else ''}"
            )
    elif a.cmd == "close-loop":
        flagged = json.loads(a.flagged.read_text()) if a.flagged and a.flagged.exists() else []
        cands = close_loop(load_annotations(a.labels), flagged)
        out = a.out or runs_dir() / "golden_candidates.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for c in cands:
                fh.write(json.dumps(asdict(c), sort_keys=True) + "\n")
        for c in cands:
            near = (
                f"  near-duplicate of {c.near_duplicate_of} ({c.similarity})"
                if c.near_duplicate_of
                else ""
            )
            print(
                f"{c.id} {c.proposed_split:5} {','.join(c.modes) or c.verdict:30.30} {c.question[:60]}{near}"
            )
        print(
            f"\n{len(cands)} candidates -> {rel(out)} (review them before adding to data/golden/)"
        )
    return 0


def short(path: Path) -> str:
    """module09_annotator_a.csv -> a"""
    return path.stem.split("_")[-1]


def render_kappa(rep) -> str:
    lines = [
        f"{len(rep.common)} cases labelled by both {rep.left} and {rep.right}",
        f"pass/fail: raw agreement {rep.observed:.2f}, Cohen's kappa {rep.kappa:.2f}",
        "",
        f"{'mode':27} kappa  both  only {rep.left:>3}  only {rep.right:>3}",
    ]
    for m, (k, both, lo, ro) in rep.per_mode.items():
        ks = "  n/a" if k != k else f"{k:5.2f}"
        lines.append(f"{m:27} {ks}  {both:4}  {lo:8}  {ro:8}")
    if rep.disagreements:
        lines += ["", "verdicts differ on: " + ", ".join(rep.disagreements)]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
