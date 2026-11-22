"""Error-analysis helpers: annotation files, failure-mode definitions, ranking, Pareto, saturation.

Tool-agnostic on purpose: annotations are a plain CSV keyed by case id, failure modes are a TOML
file you write during axial coding, and every output is CSV, text, or SVG.

    annotations CSV   case_id, trace_id, verdict, note, first_upstream, modes, annotator, annotated_at
    modes TOML        [[mode]] id, name, definition, severity (1-3), fixability, detector, owner
"""

from __future__ import annotations

import csv
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

FIELDS = [
    "case_id",
    "trace_id",
    "verdict",
    "note",
    "first_upstream",
    "modes",
    "annotator",
    "annotated_at",
]
FIXABILITY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
TAXONOMY_HEADER = [
    "rank",
    "id",
    "failure_mode",
    "definition",
    "example_trace_ids",
    "count",
    "pct",
    "severity",
    "fixability",
    "priority",
    "first_upstream_step",
    "detector",
    "owner",
]


@dataclass
class Annotation:
    case_id: str
    verdict: str  # "pass" or "fail"
    note: str = ""
    first_upstream: str = ""
    modes: list[str] = field(default_factory=list)
    annotator: str = ""
    trace_id: str = ""
    annotated_at: str = ""

    @property
    def failed(self) -> bool:
        return self.verdict == "fail"

    def to_row(self) -> dict[str, str]:
        row = {k: str(getattr(self, k)) for k in FIELDS if k != "modes"}
        row["modes"] = ";".join(self.modes)
        return row


def _split_modes(text: str) -> list[str]:
    parts = [m.strip() for m in text.replace(",", ";").split(";")]
    return [m for m in parts if m]


def load_annotations(path: Path | str) -> list[Annotation]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        verdict = (r.get("verdict") or "").strip().lower()
        if verdict not in ("pass", "fail"):
            raise ValueError(
                f"{path}: case {r.get('case_id')!r} has verdict {verdict!r}; use pass or fail"
            )
        out.append(
            Annotation(
                case_id=r["case_id"].strip(),
                verdict=verdict,
                note=(r.get("note") or "").strip(),
                first_upstream=(r.get("first_upstream") or "").strip(),
                modes=_split_modes(r.get("modes") or ""),
                annotator=(r.get("annotator") or "").strip(),
                trace_id=(r.get("trace_id") or "").strip(),
                annotated_at=(r.get("annotated_at") or "").strip(),
            )
        )
    return out


def save_annotations(path: Path | str, annotations: list[Annotation]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(a.to_row() for a in annotations)


def upsert_annotation(path: Path | str, ann: Annotation) -> None:
    """Insert or replace one annotation by case id, keeping file order (resumable sessions)."""
    rows = load_annotations(path)
    for i, r in enumerate(rows):
        if r.case_id == ann.case_id:
            rows[i] = ann
            break
    else:
        rows.append(ann)
    save_annotations(path, rows)


@dataclass(frozen=True)
class FailureMode:
    id: str
    name: str
    definition: str
    severity: int  # 1 = annoying, 2 = misleading or costly, 3 = harmful or trust-breaking
    fixability: str = "medium"  # easy | medium | hard
    detector: str = "none"  # code | judge | none (what you expect to measure it with)
    owner: str = ""


def load_modes(path: Path | str) -> dict[str, FailureMode]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    modes = {}
    for m in data.get("mode", []):
        sev = int(m["severity"])
        if sev not in (1, 2, 3):
            raise ValueError(f"mode {m['id']}: severity must be 1, 2 or 3")
        fix = m.get("fixability", "medium")
        if fix not in FIXABILITY_ORDER:
            raise ValueError(f"mode {m['id']}: fixability must be easy, medium or hard")
        modes[m["id"]] = FailureMode(
            id=m["id"],
            name=m.get("name", m["id"]),
            definition=m.get("definition", ""),
            severity=sev,
            fixability=fix,
            detector=m.get("detector", "none"),
            owner=m.get("owner", ""),
        )
    return modes


def mode_counts(annotations: list[Annotation]) -> Counter[str]:
    """Number of traces showing each mode (a mode counts once per trace)."""
    c: Counter[str] = Counter()
    for a in annotations:
        if a.failed:
            c.update(set(a.modes))
    return c


def uncoded(annotations: list[Annotation]) -> list[Annotation]:
    """Failing traces that have a note but no failure mode yet (axial coding not finished)."""
    return [a for a in annotations if a.failed and not a.modes]


@dataclass
class RankedMode:
    rank: int
    mode: FailureMode
    count: int
    pct: float  # of all annotated traces
    priority: int  # count x severity
    examples: list[str]
    first_upstream: str  # most common first upstream step among its traces


def rank_modes(
    annotations: list[Annotation], modes: dict[str, FailureMode], examples: int = 3
) -> list[RankedMode]:
    """Rank by priority = traces affected x severity; ties go to the easier fix, then the larger count."""
    counts = mode_counts(annotations)
    unknown = sorted(set(counts) - set(modes))
    if unknown:
        raise ValueError(f"modes used in annotations but not defined: {', '.join(unknown)}")
    total = len(annotations) or 1
    rows = []
    for mid, n in counts.items():
        m = modes[mid]
        tagged = [a for a in annotations if a.failed and mid in a.modes]
        ups = Counter(a.first_upstream for a in tagged if a.first_upstream)
        rows.append(
            RankedMode(
                rank=0,
                mode=m,
                count=n,
                pct=n / total,
                priority=n * m.severity,
                examples=[a.case_id for a in tagged[:examples]],
                first_upstream=ups.most_common(1)[0][0] if ups else "",
            )
        )
    rows.sort(key=lambda r: (-r.priority, FIXABILITY_ORDER[r.mode.fixability], -r.count, r.mode.id))
    for i, r in enumerate(rows, 1):
        r.rank = i
    return rows


def write_taxonomy_csv(rows: list[RankedMode], path: Path | str) -> Path:
    """The failure taxonomy sheet (see docs/eval-templates/failure-taxonomy.md)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(TAXONOMY_HEADER)
        for r in rows:
            m = r.mode
            w.writerow(
                [
                    r.rank,
                    m.id,
                    m.name,
                    m.definition,
                    " ".join(r.examples),
                    r.count,
                    f"{100 * r.pct:.0f}",
                    m.severity,
                    m.fixability,
                    r.priority,
                    r.first_upstream,
                    m.detector,
                    m.owner,
                ]
            )
    return path


def render_ranked(rows: list[RankedMode], annotations: list[Annotation]) -> str:
    n, failed = len(annotations), sum(a.failed for a in annotations)
    lines = [
        f"{n} traces annotated, {failed} failing ({100 * failed / max(n, 1):.0f}%), "
        f"{len(uncoded(annotations))} failing traces not yet coded",
        "",
        f"{'#':>2}  {'failure mode':<24} {'traces':>6} {'%':>4} {'sev':>3} {'prio':>4}  {'fix':<6}  first upstream",
    ]
    for r in rows:
        lines.append(
            f"{r.rank:>2}  {r.mode.id:<24} {r.count:>6} {100 * r.pct:>3.0f}% {r.mode.severity:>3} "
            f"{r.priority:>4}  {r.mode.fixability:<6}  {r.first_upstream}"
        )
    return "\n".join(lines)


def pareto(rows: list[RankedMode]) -> list[tuple[str, int, float]]:
    """(mode id, count, cumulative share of all mode occurrences), most frequent first."""
    by_count = sorted(rows, key=lambda r: (-r.count, r.mode.id))
    total = sum(r.count for r in by_count) or 1
    out, cum = [], 0
    for r in by_count:
        cum += r.count
        out.append((r.mode.id, r.count, cum / total))
    return out


def pareto_text(rows: list[RankedMode], width: int = 30) -> str:
    data = pareto(rows)
    top = max((c for _, c, _ in data), default=1)
    lines = [f"{'failure mode':<24} {'traces':>6}  {'':<{width}}  cumulative"]
    for mid, c, cum in data:
        bar = "#" * max(1, round(width * c / top))
        lines.append(f"{mid:<24} {c:>6}  {bar:<{width}}  {100 * cum:>4.0f}%")
    return "\n".join(lines)


def pareto_svg(rows: list[RankedMode], path: Path | str, title: str = "Failure modes") -> Path:
    """A dependency-free Pareto chart: bars for counts, a line for the cumulative share."""
    data = pareto(rows)
    w, h, left, bottom, top_pad = 760, 380, 60, 120, 40
    plot_w, plot_h = w - left - 60, h - bottom - top_pad
    top = max((c for _, c, _ in data), default=1)
    bw = plot_w / max(len(data), 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        'font-family="sans-serif" font-size="12">',
        f'<text x="{w / 2}" y="22" text-anchor="middle" font-size="15">{escape(title)}</text>',
        f'<line x1="{left}" y1="{top_pad + plot_h}" x2="{left + plot_w}" y2="{top_pad + plot_h}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top_pad}" x2="{left}" y2="{top_pad + plot_h}" stroke="#333"/>',
        f'<text x="16" y="{top_pad + plot_h / 2}" transform="rotate(-90 16 {top_pad + plot_h / 2})" '
        'text-anchor="middle">traces</text>',
        f'<text x="{w - 14}" y="{top_pad + plot_h / 2}" transform="rotate(90 {w - 14} {top_pad + plot_h / 2})" '
        'text-anchor="middle">cumulative %</text>',
    ]
    points = []
    for i, (mid, c, cum) in enumerate(data):
        x = left + i * bw
        bh = plot_h * c / top
        y = top_pad + plot_h - bh
        parts.append(
            f'<rect x="{x + bw * 0.15:.1f}" y="{y:.1f}" width="{bw * 0.7:.1f}" height="{bh:.1f}" fill="#5c6bc0"/>'
        )
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle">{c}</text>')
        lx, ly = x + bw / 2, top_pad + plot_h + 10
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" transform="rotate(40 {lx:.1f} {ly:.1f})">{escape(mid)}</text>'
        )
        points.append((x + bw / 2, top_pad + plot_h * (1 - cum)))
    if points:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="#e65100" stroke-width="2"/>')
        parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#e65100"/>' for x, y in points]
    for pct in (0, 50, 80, 100):
        y = top_pad + plot_h * (1 - pct / 100)
        parts.append(f'<text x="{left + plot_w + 6}" y="{y + 4:.1f}" fill="#e65100">{pct}%</text>')
    y80 = top_pad + plot_h * 0.2
    parts.append(
        f'<line x1="{left}" y1="{y80:.1f}" x2="{left + plot_w}" y2="{y80:.1f}" stroke="#e65100" '
        'stroke-dasharray="4 4" stroke-width="1"/>'
    )
    parts.append("</svg>")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path


def saturation_curve(annotations: list[Annotation]) -> list[int]:
    """Distinct failure modes seen after each annotated trace, in annotation (file) order."""
    seen: set[str] = set()
    curve = []
    for a in annotations:
        if a.failed:
            seen.update(a.modes)
        curve.append(len(seen))
    return curve


def last_new_mode_at(curve: list[int]) -> int:
    """1-based position of the trace that introduced the last new mode (0 if none)."""
    last = 0
    for i, v in enumerate(curve):
        if i == 0 and v > 0 or i > 0 and v > curve[i - 1]:
            last = i + 1
    return last


def render_saturation(curve: list[int], step: int = 10) -> str:
    lines = ["traces reviewed  distinct modes"]
    for i in range(step, len(curve) + 1, step):
        lines.append(f"{i:>15}  {curve[i - 1]:>3}  " + "#" * curve[i - 1])
    if len(curve) % step:
        lines.append(f"{len(curve):>15}  {curve[-1]:>3}  " + "#" * curve[-1])
    last = last_new_mode_at(curve)
    lines.append(
        f"\nlast new mode appeared at trace {last}; {len(curve) - last} traces since then without a new mode"
    )
    return "\n".join(lines)


def first_upstream_counts(annotations: list[Annotation]) -> Counter[str]:
    return Counter(a.first_upstream or "(not given)" for a in annotations if a.failed)


@dataclass
class Agreement:
    common: int
    both_fail: int
    both_pass: int
    only_mine_fail: list[str]
    only_ref_fail: list[str]

    @property
    def agreement(self) -> float:
        return (self.both_fail + self.both_pass) / max(self.common, 1)


def compare_verdicts(mine: list[Annotation], ref: list[Annotation]) -> Agreement:
    """Pass/fail agreement on the cases both files label. Mode names may differ, so compare
    them separately (see `mode_overlap`)."""
    r = {a.case_id: a for a in ref}
    common = [a for a in mine if a.case_id in r]
    return Agreement(
        common=len(common),
        both_fail=sum(a.failed and r[a.case_id].failed for a in common),
        both_pass=sum(not a.failed and not r[a.case_id].failed for a in common),
        only_mine_fail=[a.case_id for a in common if a.failed and not r[a.case_id].failed],
        only_ref_fail=[a.case_id for a in common if not a.failed and r[a.case_id].failed],
    )


def mode_overlap(mine: list[Annotation], ref: list[Annotation]) -> dict[str, Counter[str]]:
    """For each reference mode, which of YOUR modes you gave the same traces. Shows merges and
    splits between two taxonomies without forcing the names to match."""
    m = {a.case_id: a for a in mine}
    out: dict[str, Counter[str]] = {}
    for a in ref:
        if not a.failed or a.case_id not in m:
            continue
        for rm in a.modes:
            mine_modes = m[a.case_id].modes or (
                ["(pass)"] if not m[a.case_id].failed else ["(uncoded)"]
            )
            out.setdefault(rm, Counter()).update(mine_modes)
    return dict(sorted(out.items()))
