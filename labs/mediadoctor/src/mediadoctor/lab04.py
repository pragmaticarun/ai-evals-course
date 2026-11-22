"""Module 4 lab: synthetic test data for MediaDoctor, offline in replay mode.

    uv run mediadoctor-lab04 dims                       # dimensions, rules, size of the space
    uv run mediadoctor-lab04 tuples --strategy pairwise # compare full / sample / pairwise
    uv run mediadoctor-lab04 naive                      # what "give me 50 questions" produces
    uv run mediadoctor-lab04 generate --out runs/m4_v1.jsonl   # tuples -> queries -> dedup -> splits
    uv run mediadoctor-lab04 check                      # does each query match its tuple?
    uv run mediadoctor-lab04 coverage --rows topic --cols evidence
    uv run mediadoctor-lab04 gaps                       # seed from real queries: fill only the gaps
    uv run mediadoctor-lab04 agent --out runs/m4_traces.jsonl   # run the module 2 agent on the dev split
    uv run mediadoctor-lab04 by-dimension --dim ambiguity       # failure rate per dimension value

Replay mode (default) needs no API key; the synth responses in fixtures/recorded/ are
synthetic-authored (see scripts/author_module04_fixtures.py). With a key, `--batch` sends the
query-writing requests through the Message Batches API in record or live mode.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evalkit import LLM, Mode, Tracer, repo_root, text_of
from evalkit.annotate import load_annotations
from evalkit.synth import (
    Space,
    assign_splits,
    coverage_matrix,
    create_many,
    dedup,
    diversity_report,
    full_product,
    leakage_pairs,
    load_space,
    pair_coverage,
    pairwise_tuples,
    render_diversity,
    sample_tuples,
    stratified_sample,
    value_counts,
    write_jsonl,
)
from evalkit.trace import VIRTUAL_EPOCH_NS, SeededIds, VirtualClock
from evalkit.viewer import render_table
from mediadoctor.synth_spec import (
    KB_FOR_TOPIC,
    SYNTH_NAMESPACE,
    artefacts_for,
    build_naive_request,
    build_synth_request,
    expected_tools,
    premise_for,
    style_examples,
)
from mediadoctor.toolagent import run_agent

SEED = 4
N_TUPLES = 200
DEDUP_THRESHOLD = 0.6  # word-trigram Jaccard on the prose; see the module 4 exercises
DEDUP_WITHIN = ("evidence", "ambiguity")  # never drop a query for resembling a different test case
GROUP_THRESHOLD = 0.35  # similar queries share a split, so near-duplicates cannot leak
AGENT_NAMESPACE = "mediadoctor-m4"


def space_path() -> Path:
    return repo_root() / "config" / "synth" / "mediadoctor.toml"


def dataset_path() -> Path:
    return repo_root() / "data" / "datasets" / "module04_v1.jsonl"


def manifest_path() -> Path:
    return repo_root() / "data" / "datasets" / "module04_v1.manifest.json"


def dev_reference_path() -> Path:
    return repo_root() / "data" / "labels" / "module04_dev_reference.csv"


def load_default_space() -> Space:
    return load_space(space_path())


# --- Step 1: tuples ---------------------------------------------------------------------------


def make_tuples(space: Space, n: int = N_TUPLES, seed: int = SEED) -> list[dict[str, str]]:
    """All-pairs coverage first, then fill to n, stratified by topic so small topics get a fair share."""
    base = pairwise_tuples(space, seed=seed)
    return base + stratified_sample(space, n - len(base), by="topic", seed=seed, exclude=base)


# --- Step 2: queries ----------------------------------------------------------------------------


def generate_queries(
    tuples: list[dict[str, str]], llm: LLM | None = None, use_batch: bool = True
) -> list[dict[str, Any]]:
    llm = llm or LLM(namespace=SYNTH_NAMESPACE)
    examples = style_examples()
    requests = {f"t{i:03d}": build_synth_request(t, examples) for i, t in enumerate(tuples, 1)}
    responses = create_many(llm, requests, use_batch=use_batch)
    rows = []
    for (tid, _), t in zip(requests.items(), tuples, strict=True):
        art = artefacts_for(t)
        rows.append(
            {
                "tuple_id": tid,
                **t,
                **art,
                "premise": premise_for(t, art),
                "query": text_of(responses[tid]).strip(),
            }
        )
    return rows


# --- Step 3: dedup, splits, freeze ---------------------------------------------------------------


def build_dataset(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items = [(r["tuple_id"], r["query"]) for r in rows]
    by_id = {r["tuple_id"]: r for r in rows}
    d = dedup(
        items, threshold=DEDUP_THRESHOLD, key=lambda i: tuple(by_id[i][k] for k in DEDUP_WITHIN)
    )
    kept_ids = set(d.kept)
    kept = [r for r in rows if r["tuple_id"] in kept_ids]
    kept_items = [(r["tuple_id"], r["query"]) for r in kept]
    splits = assign_splits(kept_items, salt="mediadoctor-v1", group_threshold=GROUP_THRESHOLD)
    dataset = []
    for i, r in enumerate(kept, 1):
        row = {k: v for k, v in r.items() if v is not None}
        row.update(
            id=f"m4q{i:03d}",
            split=splits[r["tuple_id"]],
            question=r["query"],
            expected_tools=expected_tools(r),
            expected_kb=[KB_FOR_TOPIC[r["topic"]]],
            source="synthetic-authored",
        )
        del row["query"]
        dataset.append(row)
    report = {
        "generated": len(rows),
        "dropped_as_duplicates": d.dropped,
        "kept": len(dataset),
        "splits": dict(Counter(r["split"] for r in dataset)),
        "leakage_pairs": leakage_pairs(kept_items, splits, GROUP_THRESHOLD),
    }
    return dataset, report


def check_queries(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Does each query do what its tuple asked? Returns (id, problem) pairs; empty is good.

    A writer model can drift: correct the premise it was told to state, name the file a
    missing-detail query should hide, or drop the log it should paste. Cheap checks catch most of it.
    """
    problems = []
    for r in rows:
        q = r.get("question", r.get("query", ""))
        low = q.lower()
        rid = r.get("id", r.get("tuple_id", "?"))
        named = [r[k] for k in ("file", "device") if r.get(k)]
        if r["ambiguity"] == "missing-detail":
            problems += [
                (rid, f"names {n} but should leave it unstated") for n in named if n.lower() in low
            ]
        else:
            problems += [(rid, f"does not mention {n}") for n in named if n.lower() not in low]
            if r.get("log") and not re.search(r"^\d\d-\d\d \d\d:\d\d", q, re.M):
                problems.append((rid, "should paste log lines but has none"))
        if r.get("premise") and r["premise"].lower().split()[-1] not in low:
            problems.append((rid, "does not state its premise"))
        if any(t in low for t in ("i'm experiencing", "could you please", "best practices")):
            problems.append((rid, "LLM-style phrasing"))
    return problems


def load_dataset(path: Path | str | None = None) -> list[dict[str, Any]]:
    with Path(path or dataset_path()).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --- Naive baseline ---------------------------------------------------------------------------------

TOPIC_KEYWORDS = {
    "av1-playback": ("av1", "4k", "stutter", "choppy", "decod"),
    "hdr-colour": ("hdr", "washed", "colour", "color", "black screen"),
    "mp4-startup": ("start", "startup", "moov", "slow to"),
    "av-sync": ("sync", "lip", "audio is ahead"),
    "codec-limits": ("mediacodec", "codec", "thumbnail"),
    "live-stream": ("live", "resum", "background"),
    "audio-focus": ("audio focus", "phone call", "calls", "keeps playing"),
    "drm-resolution": ("drm", "widevine", "sd ", "480p", " hd "),
}
NAMES = re.compile(r"\b[\w-]+\.(mp4|mkv|txt)\b|lumen-l3|atlas-a1|\d\d-\d\d \d\d:\d\d:\d\d")


def tag_topics(text: str) -> list[str]:
    low = f" {text.lower()} "
    return [t for t, kws in TOPIC_KEYWORDS.items() if any(k in low for k in kws)]


def naive_queries(llm: LLM | None = None) -> list[str]:
    llm = llm or LLM(namespace=SYNTH_NAMESPACE)
    resp = llm.create(**build_naive_request())
    return [ln.strip() for ln in text_of(resp).splitlines() if ln.strip()]


def topic_coverage(texts: list[str]) -> Counter[str]:
    c: Counter[str] = Counter()
    for t in texts:
        c.update(tag_topics(t))
    return c


# --- Agent run on the dev split (module 2 agent, module 3 analysis) ----------------------------


def scenario_for(row: dict[str, Any]) -> str | None:
    """Which module 3 scenario a dataset row exercises (None: not in the agent slice)."""
    topic, ev, dev, f = row["topic"], row["evidence"], row.get("device"), row.get("file", "")
    if topic in ("av1-playback", "hdr-colour"):
        prefix = "av1" if topic == "av1-playback" else "hdr"
        if dev:
            return f"{prefix}-{'lumen' if dev == 'lumen-l3' else 'atlas'}"
        return ("av1-api" if prefix == "av1" else "hdr-display-api") if ev == "none" else None
    if topic == "mp4-startup" and f:
        return "faststart" if "faststart" in f else "latemoov"
    if topic == "av-sync" and f:
        return "avoffset"
    if topic == "codec-limits":
        return {"log": "thumbs", "device": "main10"}.get(ev)
    if topic == "live-stream" and ev == "log":
        return "live"
    if topic == "audio-focus":
        return "audiofocus"
    if topic == "drm-resolution" and dev:
        return "widevine"
    return None


def agent_slice(dataset: list[dict[str, Any]], split: str = "dev") -> list[dict[str, Any]]:
    return [r for r in dataset if r["split"] == split and scenario_for(r)]


def run_slice(rows: list[dict[str, Any]], llm: LLM | None = None) -> list[dict[str, Any]]:
    llm = llm or LLM(namespace=AGENT_NAMESPACE)
    live = llm.mode is not Mode.REPLAY
    spans: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        tracer = (
            Tracer()
            if live
            else Tracer(
                clock=VirtualClock(VIRTUAL_EPOCH_NS + i * 60_000_000_000),
                ids=SeededIds(f"mediadoctor-lab04:{r['id']}"),
            )
        )
        run_agent(r["question"], llm=llm, tracer=tracer, case_id=r["id"])
        spans.extend(tracer.span_dicts())
    return spans


def failure_by_dimension(
    labels_path: Path | str, dataset: list[dict[str, Any]], dim: str
) -> dict[str, tuple[int, int, Counter[str]]]:
    """{value: (failing, labelled, mode counts)} for one dimension."""
    rows = {r["id"]: r for r in dataset}
    out: dict[str, list[Any]] = defaultdict(lambda: [0, 0, Counter()])
    for a in load_annotations(labels_path):
        if a.case_id not in rows:
            continue
        v = rows[a.case_id][dim]
        out[v][1] += 1
        if a.failed:
            out[v][0] += 1
            out[v][2].update(a.modes)
    return {k: (v[0], v[1], v[2]) for k, v in sorted(out.items())}


# --- CLI ----------------------------------------------------------------------------------------------


def _print_generation(dataset: list[dict[str, Any]], report: dict[str, Any], space: Space) -> None:
    print(
        f"{report['generated']} queries generated, {len(report['dropped_as_duplicates'])} dropped as near-duplicates, {report['kept']} kept"
    )
    for a, b, s in report["dropped_as_duplicates"][:5]:
        print(f"  dropped {a} (similarity {s:.2f} to {b})")
    print(
        f"splits: {report['splits']}; near-duplicate pairs across splits: {len(report['leakage_pairs'])}"
    )
    print()
    print(render_diversity("dataset v1", diversity_report([r["question"] for r in dataset])))
    print()
    print(coverage_matrix(dataset, space, "topic", "evidence"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mediadoctor-lab04", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dims", help="dimensions, rules, and the size of the space")
    t = sub.add_parser("tuples", help="compare tuple strategies")
    t.add_argument("--strategy", choices=["full", "sample", "pairwise", "course"], default="course")
    t.add_argument("--n", type=int, default=50)
    t.add_argument("--seed", type=int, default=SEED)
    sub.add_parser("naive", help="analyse the one-prompt baseline")
    g = sub.add_parser("generate", help="tuples -> queries -> dedup -> splits")
    g.add_argument("--out", help="write the dataset JSONL here")
    g.add_argument("--batch", action="store_true", help="use the Message Batches API (record/live)")
    k = sub.add_parser("check", help="check each query against its tuple")
    k.add_argument("--dataset")
    c = sub.add_parser("coverage", help="coverage matrix for two dimensions")
    c.add_argument("--rows", default="topic")
    c.add_argument("--cols", default="evidence")
    c.add_argument("--dataset")
    sub.add_parser("gaps", help="coverage of the beta queries and the tuples that fill their gaps")
    a = sub.add_parser("agent", help="run the module 2 agent on the dev split slice")
    a.add_argument("--split", default="dev")
    a.add_argument("--out")
    b = sub.add_parser("by-dimension", help="failure rate per value of one dimension")
    b.add_argument("--labels")
    b.add_argument("--dim", default="ambiguity")
    args = p.parse_args(argv)
    space = load_default_space()

    if args.cmd == "dims":
        for d in space.dimensions:
            print(f"{d.name:<10} {len(d.values)}  {', '.join(d.values)}")
        print(
            f"\nfull product {space.product_size}; valid after {len(space.rules)} rules: {len(full_product(space))}"
        )
        for r in space.rules:
            print(f"  - {r.reason}")
        return 0
    if args.cmd == "tuples":
        if args.strategy == "full":
            tuples = full_product(space)
        elif args.strategy == "sample":
            tuples = sample_tuples(space, args.n, args.seed)
        elif args.strategy == "pairwise":
            tuples = pairwise_tuples(space, args.seed)
        else:
            tuples = make_tuples(space)
        cov, feas = pair_coverage(tuples, space)
        print(
            f"{args.strategy}: {len(tuples)} tuples, value pairs covered {cov}/{feas} ({100 * cov / feas:.0f}%)"
        )
        print(coverage_matrix(tuples, space, "topic", "evidence"))
        return 0
    if args.cmd == "naive":
        qs = naive_queries()
        print(render_diversity("naive prompt", diversity_report(qs)))
        cov = topic_coverage(qs)
        print("\ntopics mentioned (keyword tagger):")
        for topic in space.dim("topic").values:
            print(f"  {topic:<16} {cov[topic]}")
        named = sum(bool(NAMES.search(q)) for q in qs)
        print(f"\nqueries naming a file, device, or pasting a log: {named}/{len(qs)}")
        return 0
    if args.cmd == "generate":
        rows = generate_queries(make_tuples(space), use_batch=args.batch)
        dataset, report = build_dataset(rows)
        _print_generation(dataset, report, space)
        if args.out:
            print(f"\nwrote {write_jsonl(args.out, dataset)}")
        return 0
    if args.cmd == "check":
        ds = load_dataset(args.dataset)
        problems = check_queries(ds)
        for rid, msg in problems:
            print(f"{rid}  {msg}")
        print(f"{len(ds)} queries checked, {len(problems)} problems")
        return 0 if not problems else 1
    if args.cmd == "coverage":
        ds = load_dataset(args.dataset)
        print(coverage_matrix(ds, space, args.rows, args.cols))
        for split in ("train", "dev", "test"):
            part = [r for r in ds if r["split"] == split]
            cov, feas = pair_coverage(part, space)
            print(f"{split:<5} {len(part):>3} queries, value pairs covered {cov}/{feas}")
        return 0
    if args.cmd == "gaps":
        beta = [{k: e[k] for k in space.names} for e in style_examples()]
        cov, feas = pair_coverage(beta, space)
        print(f"{len(beta)} beta queries cover {cov}/{feas} value pairs")
        print(coverage_matrix(beta, space, "topic", "evidence"))
        fill = pairwise_tuples(space, seed=SEED, start=beta)
        cov2, _ = pair_coverage(beta + fill, space)
        print(f"\n{len(fill)} generated tuples fill the gaps: {cov2}/{feas} pairs covered")
        missing = [
            d.name + "=" + v
            for d in space.dimensions
            for v in d.values
            if value_counts(beta, d.name)[v] == 0
        ]
        print("values the beta queries never use: " + ", ".join(missing))
        return 0
    if args.cmd == "agent":
        rows = agent_slice(load_dataset(), args.split)
        spans = run_slice(rows)
        print(render_table(spans))
        if args.out:
            write_jsonl(args.out, spans)
            print(f"\nwrote {len(spans)} spans for {len(rows)} queries to {args.out}")
        return 0
    if args.cmd == "by-dimension":
        res = failure_by_dimension(args.labels or dev_reference_path(), load_dataset(), args.dim)
        print(f"{args.dim:<16} {'failing':>8}  modes")
        for v, (fail, n, modes) in res.items():
            print(f"{v:<16} {fail:>3}/{n:<4}  {dict(modes) or ''}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
