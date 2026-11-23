"""Synthetic test data: dimensions, tuples, coverage, dedup, diversity, splits, batch generation.

The workflow taught in module 4:

    dimensions (TOML)  ->  tuples (full / sampled / pairwise, minus impossible combos)
                       ->  one model request per tuple (cheap synth model)  ->  queries
                       ->  dedup + diversity report  ->  coverage matrix  ->  frozen, split dataset

Nothing here is specific to MediaDoctor; the app supplies the prompt that turns a tuple into a
request (see mediadoctor.lab04).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
import re
import time
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalkit.config import check_live_model, to_live_model
from evalkit.llm import LLM, Mode, _to_dict

Tuple = dict[str, str]
Pair = tuple[tuple[str, str], tuple[str, str]]

# --- Dimensions and constraints -----------------------------------------------------------------


@dataclass(frozen=True)
class Dimension:
    name: str
    values: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class Rule:
    """Excludes tuples that match every `when` condition and any `forbid` condition."""

    when: dict[str, tuple[str, ...]]
    forbid: dict[str, tuple[str, ...]]
    reason: str = ""

    def violated_by(self, t: dict[str, str]) -> bool:
        """True only once every dimension the rule mentions is assigned (safe for partial tuples)."""
        if not all(k in t for k in (*self.when, *self.forbid)):
            return False
        if not all(t[k] in v for k, v in self.when.items()):
            return False
        return any(t[k] in v for k, v in self.forbid.items())


@dataclass
class Space:
    dimensions: list[Dimension]
    rules: list[Rule] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        return [d.name for d in self.dimensions]

    def dim(self, name: str) -> Dimension:
        return next(d for d in self.dimensions if d.name == name)

    def broken_rule(self, t: dict[str, str]) -> Rule | None:
        return next((r for r in self.rules if r.violated_by(t)), None)

    def valid(self, t: dict[str, str]) -> bool:
        return self.broken_rule(t) is None

    @property
    def product_size(self) -> int:
        n = 1
        for d in self.dimensions:
            n *= len(d.values)
        return n


def _as_tuple(v: Any) -> tuple[str, ...]:
    return tuple(v) if isinstance(v, list) else (v,)


def load_space(path: Path | str) -> Space:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    dims = [
        Dimension(d["name"], tuple(d["values"]), d.get("description", ""))
        for d in data["dimension"]
    ]
    names = {d.name: set(d.values) for d in dims}
    rules = []
    for r in data.get("exclude", []):
        when = {k: _as_tuple(v) for k, v in r.get("when", {}).items()}
        forbid = {k: _as_tuple(v) for k, v in r["forbid"].items()}
        for k, vals in (*when.items(), *forbid.items()):
            unknown = set(vals) - names.get(k, set())
            if k not in names or unknown:
                raise ValueError(f"rule {r.get('reason', '')!r} uses unknown {k}={sorted(unknown)}")
        rules.append(Rule(when, forbid, r.get("reason", "")))
    return Space(dims, rules)


# --- Tuple strategies ----------------------------------------------------------------------------


def full_product(space: Space) -> list[Tuple]:
    """Every combination that breaks no rule, in a stable order."""
    out = []
    for combo in itertools.product(*(d.values for d in space.dimensions)):
        t = dict(zip(space.names, combo, strict=True))
        if space.valid(t):
            out.append(t)
    return out


def sample_tuples(space: Space, n: int, seed: int = 0) -> list[Tuple]:
    """n distinct valid tuples, uniformly at random (all of them if fewer exist)."""
    valid = full_product(space)
    return random.Random(seed).sample(valid, min(n, len(valid)))


def stratified_sample(
    space: Space, n: int, by: str, seed: int = 0, exclude: Iterable[Tuple] = ()
) -> list[Tuple]:
    """n valid tuples spread as evenly as possible over the values of one dimension.

    Uniform sampling over *valid tuples* over-represents values that allow many combinations
    (a topic with five kinds of evidence) and starves values with few (a topic with one).
    Stratifying on the dimension you care most about fixes that.
    """
    rng = random.Random(seed)
    skip = {tuple(sorted(t.items())) for t in exclude}
    pools: dict[str, list[Tuple]] = {v: [] for v in space.dim(by).values}
    for t in full_product(space):
        if tuple(sorted(t.items())) not in skip:
            pools[t[by]].append(t)
    for pool in pools.values():
        rng.shuffle(pool)
    out: list[Tuple] = []
    while len(out) < n and any(pools.values()):
        for v in space.dim(by).values:
            if pools[v] and len(out) < n:
                out.append(pools[v].pop())
    return out


def pairs_of(t: Tuple, names: list[str]) -> set[Pair]:
    return {((a, t[a]), (b, t[b])) for a, b in itertools.combinations(names, 2)}


def feasible_pairs(space: Space) -> set[Pair]:
    """Value pairs that occur in at least one valid tuple (the ones worth covering)."""
    out: set[Pair] = set()
    for t in full_product(space):
        out |= pairs_of(t, space.names)
    return out


def pairwise_tuples(space: Space, seed: int = 0, start: Iterable[Tuple] = ()) -> list[Tuple]:
    """Greedy all-pairs covering: every feasible pair of values appears in at least one tuple.

    Each step takes the first uncovered pair and adds the valid tuple containing it that covers
    the most still-uncovered pairs (ties broken by a seeded shuffle). Pass `start` (for example
    tuples of real queries you already have) to fill only the gaps they leave. Not minimal, but
    deterministic and usually close to the size of a hand-built covering array.
    """
    names = space.names
    rng = random.Random(seed)
    candidates = full_product(space)
    rng.shuffle(candidates)
    cand_pairs = [pairs_of(t, names) for t in candidates]
    uncovered = feasible_pairs(space)
    for t in start:
        uncovered -= pairs_of(t, names)
    chosen: list[Tuple] = []
    while uncovered:
        target = min(uncovered)
        best, best_gain = -1, -1
        for i, ps in enumerate(cand_pairs):
            if target in ps:
                gain = len(ps & uncovered)
                if gain > best_gain:
                    best, best_gain = i, gain
        chosen.append(candidates[best])
        uncovered -= cand_pairs[best]
    return chosen


def pair_coverage(tuples: Iterable[Tuple], space: Space) -> tuple[int, int]:
    """(feasible pairs covered, feasible pairs)."""
    feas = feasible_pairs(space)
    seen: set[Pair] = set()
    for t in tuples:
        seen |= pairs_of(t, space.names)
    return len(seen & feas), len(feas)


# --- Coverage reports ----------------------------------------------------------------------------


def value_counts(rows: Iterable[Tuple], dim: str) -> Counter[str]:
    return Counter(r[dim] for r in rows)


def coverage_matrix(rows: Iterable[Tuple], space: Space, row_dim: str, col_dim: str) -> str:
    """Counts per (row value, column value). `x` marks combinations the rules make impossible,
    so a `0` is a real gap rather than an excluded cell."""
    rows = list(rows)
    rvals, cvals = space.dim(row_dim).values, space.dim(col_dim).values
    feas = feasible_pairs(space)
    counts = Counter((r[row_dim], r[col_dim]) for r in rows)
    width = max(5, *(len(c) for c in cvals))
    rw = max(len(row_dim), *(len(v) for v in rvals))
    lines = [f"{row_dim:<{rw}}  " + " ".join(f"{c:>{width}}" for c in cvals) + f"  {'total':>5}"]
    gaps = 0
    for rv in rvals:
        cells = []
        for cv in cvals:
            key = (
                ((row_dim, rv), (col_dim, cv))
                if row_dim < col_dim
                else ((col_dim, cv), (row_dim, rv))
            )
            pair_ok = key in feas or ((row_dim, rv), (col_dim, cv)) in feas
            n = counts[(rv, cv)]
            if not pair_ok:
                cells.append(f"{'x':>{width}}")
            else:
                cells.append(f"{n:>{width}}")
                gaps += n == 0
        total = sum(counts[(rv, cv)] for cv in cvals)
        lines.append(f"{rv:<{rw}}  " + " ".join(cells) + f"  {total:>5}")
    lines.append(f"\n{gaps} possible cells with no examples; x = excluded by a rule")
    return "\n".join(lines)


# --- Generation: one request per tuple, optionally through the Message Batches API -------------


def create_many(
    llm: LLM,
    requests: dict[str, dict[str, Any]],
    use_batch: bool = True,
    poll_seconds: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, dict[str, Any]]:
    """Run many Messages requests; returns {custom_id: response}.

    replay: every response comes from the fixture store, as with LLM.create.
    record/live with use_batch: one Message Batch (half price, results within 24 hours), polled
    until it ends; in record mode each result is saved under its own request key, so later
    replays look identical to one-by-one calls. Without use_batch: plain sequential calls.
    """
    if llm.mode is Mode.REPLAY or not use_batch:
        return {cid: llm.create(**req) for cid, req in requests.items()}
    # As LLM.create does in record and live: the `[live]` model only, checked before sending.
    requests = {cid: to_live_model(req) for cid, req in requests.items()}
    for req in requests.values():
        check_live_model(req)
    client = llm.client
    batch = client.messages.batches.create(
        requests=[{"custom_id": cid, "params": req} for cid, req in requests.items()]
    )
    batch_id = _to_dict(batch)["id"]
    while _to_dict(client.messages.batches.retrieve(batch_id))["processing_status"] != "ended":
        sleep(poll_seconds)
    out: dict[str, dict[str, Any]] = {}
    for item in client.messages.batches.results(batch_id):
        item = _to_dict(item)
        result = item["result"]
        if result.get("type") != "succeeded":
            raise RuntimeError(f"batch request {item['custom_id']} ended as {result.get('type')}")
        response = _to_dict(result["message"])
        out[item["custom_id"]] = response
        llm.calls += 1
        if llm.mode is Mode.RECORD:
            llm.store.put(requests[item["custom_id"]], response, source=llm.source)
    missing = set(requests) - set(out)
    if missing:
        raise RuntimeError(f"batch returned no result for {sorted(missing)[:5]}")
    return out


# --- Text similarity, dedup, diversity -------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9_.]+")
# Pasted logcat lines ("11-20 14:02:11.309  8123 ..."): ignored for similarity, so two different
# questions that paste the same log are not mistaken for duplicates.
_LOG_LINE = re.compile(r"^\s*\d\d-\d\d \d\d:\d\d:\d\d\.\d+\s")


def prose(text: str) -> str:
    """The part of a message the user wrote: pasted log lines removed."""
    return "\n".join(ln for ln in text.splitlines() if not _LOG_LINE.match(ln))


def normalize(text: str) -> str:
    return " ".join(_WORD.findall(prose(text).lower()))


def shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    words = normalize(text).split()
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def similarity(a: str, b: str, n: int = 3) -> float:
    """Word n-gram Jaccard similarity: 1.0 identical, around 0.5 heavy overlap, near 0 unrelated."""
    return jaccard(shingles(a, n), shingles(b, n))


@dataclass
class DedupResult:
    kept: list[str]
    dropped: list[tuple[str, str, float]]  # (dropped id, kept id it duplicates, similarity)


def dedup(
    items: list[tuple[str, str]],
    threshold: float = 0.5,
    n: int = 3,
    key: Callable[[str], Any] | None = None,
) -> DedupResult:
    """Keep the first of every group of near-duplicates (similarity >= threshold), in order.

    `key(id)` optionally partitions the items: only items with the same key are compared. Use it to
    protect queries whose text is close but whose tuples differ in a dimension that matters (a
    pasted log versus "I can grab logs" is a different test case, however similar the prose).
    """
    kept: list[tuple[str, set, Any]] = []
    dropped = []
    for iid, text in items:
        sh = shingles(text, n)
        k = key(iid) if key else None
        best = max(
            ((kid, jaccard(sh, s)) for kid, s, kk in kept if kk == k),
            key=lambda x: x[1],
            default=None,
        )
        if best and best[1] >= threshold:
            dropped.append((iid, best[0], round(best[1], 3)))
        else:
            kept.append((iid, sh, k))
    return DedupResult([kid for kid, _, _ in kept], dropped)


LLM_TELLS = (
    "i'm experiencing",
    "i am experiencing",
    "i'm encountering",
    "could you please",
    "can you help me",
    "i hope",
    "delve",
    "seamless",
    "comprehensive",
    "best practices",
    "how can i ensure",
    "what steps should i take",
    "any insights",
)


def diversity_report(texts: list[str]) -> dict[str, Any]:
    """Cheap diversity signals. Compare two sets with them; no single number is 'good'."""
    norm = [normalize(t).split() for t in texts]
    unigrams = [w for ws in norm for w in ws]
    bigrams = [tuple(ws[i : i + 2]) for ws in norm for i in range(len(ws) - 1)]
    sh = [shingles(t) for t in texts]
    sims = [jaccard(a, b) for a, b in itertools.combinations(sh, 2)]
    lengths = [len(ws) for ws in norm]
    openers = Counter(" ".join(ws[:2]) for ws in norm if ws)
    low = [t.lower() for t in texts]
    return {
        "n": len(texts),
        "distinct_1": round(len(set(unigrams)) / max(len(unigrams), 1), 3),
        "distinct_2": round(len(set(bigrams)) / max(len(bigrams), 1), 3),
        "mean_similarity": round(sum(sims) / max(len(sims), 1), 3),
        "pairs_over_0.5": sum(s >= 0.5 for s in sims),
        "words_min_mean_max": (
            min(lengths, default=0),
            round(sum(lengths) / max(len(lengths), 1), 1),
            max(lengths, default=0),
        ),
        "top_openers": openers.most_common(3),
        "share_top_opener": round(openers.most_common(1)[0][1] / max(len(texts), 1), 3)
        if openers
        else 0.0,
        "llm_tells": sum(any(tell in t for tell in LLM_TELLS) for t in low),
    }


def render_diversity(name: str, rep: dict[str, Any]) -> str:
    lo, mean, hi = rep["words_min_mean_max"]
    return "\n".join(
        [
            f"{name}: {rep['n']} queries",
            f"  distinct words / bigrams     {rep['distinct_1']:.3f} / {rep['distinct_2']:.3f}",
            f"  mean pairwise similarity     {rep['mean_similarity']:.3f}  ({rep['pairs_over_0.5']} pairs >= 0.5)",
            f"  words per query              min {lo}, mean {mean}, max {hi}",
            f"  most common opening          {rep['top_openers'][0][0]!r} ({100 * rep['share_top_opener']:.0f}% of queries)"
            if rep["top_openers"]
            else "  most common opening          -",
            f"  queries with LLM-style tells {rep['llm_tells']}",
        ]
    )


# --- Splits and leakage -----------------------------------------------------------------------------


def _clusters(items: list[tuple[str, str]], threshold: float) -> dict[str, str]:
    """Map each id to a cluster representative: items linked by similarity >= threshold."""
    parent = {i: i for i, _ in items}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    sh = [(i, shingles(t)) for i, t in items]
    for (a, sa), (b, sb) in itertools.combinations(sh, 2):
        if jaccard(sa, sb) >= threshold:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    return {i: find(i) for i, _ in items}


def assign_splits(
    items: list[tuple[str, str]],
    fractions: dict[str, float] | None = None,
    salt: str = "v1",
    group_threshold: float = 0.35,
) -> dict[str, str]:
    """Deterministic split by hashing a group key. Similar queries (similarity >= group_threshold)
    share a group, so near-duplicates cannot straddle train and test (leakage)."""
    fractions = fractions or {"train": 0.6, "dev": 0.2, "test": 0.2}
    groups = _clusters(items, group_threshold)
    out = {}
    for iid, _ in items:
        h = int(hashlib.sha256(f"{salt}:{groups[iid]}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        acc = 0.0
        for name, frac in fractions.items():
            acc += frac
            if h <= acc:
                out[iid] = name
                break
        else:
            out[iid] = list(fractions)[-1]
    return out


def leakage_pairs(
    items: list[tuple[str, str]], splits: dict[str, str], threshold: float = 0.35
) -> list[tuple[str, str, float]]:
    """Pairs of similar queries that ended up in different splits."""
    sh = {i: shingles(t) for i, t in items}
    out = []
    for (a, _), (b, _) in itertools.combinations(items, 2):
        if splits[a] != splits[b]:
            s = jaccard(sh[a], sh[b])
            if s >= threshold:
                out.append((a, b, round(s, 3)))
    return out


def file_sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_jsonl(path: Path | str, rows: Iterable[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return path
