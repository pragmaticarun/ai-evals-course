"""Files behind the app: traces, the queue, failure modes, and labels per annotator."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from evalkit.annotate import (
    Annotation,
    FailureMode,
    load_annotations,
    load_modes,
    save_annotations,
)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MODE_RE = re.compile(r"^[a-z][a-z0-9-]{1,47}$")
Trace = list[dict[str, Any]]


def valid_name(name: str) -> bool:
    """Annotator names become file names, so only lowercase letters, digits, - and _ are allowed."""
    return bool(NAME_RE.match(name or ""))


def load_spans(path: Path) -> dict[str, Trace]:
    """trace id -> spans, in file order."""
    out: dict[str, Trace] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                s = json.loads(line)
                out.setdefault(s["trace_id"], []).append(s)
    return out


def root_of(trace: Trace) -> dict[str, Any]:
    return next(s for s in trace if not s.get("parent_span_id"))


@dataclass
class Item:
    """One queue entry. Only `case_id` and `trace_id` are required in the queue file."""

    case_id: str
    trace_id: str
    reasons: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    context: dict[str, str] = field(default_factory=dict)  # shown only when context is revealed


def load_queue(path: Path | None, traces: dict[str, Trace]) -> list[Item]:
    """Queue JSONL rows need `trace_id` and `request_id` (or `case_id`). Without a queue file, every
    trace is reviewed in file order."""
    if path is None:
        return [
            Item(str(root_of(t)["attributes"].get("mediadoctor.case.id") or tid), tid)
            for tid, t in traces.items()
        ]
    items = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            ctx = {
                k: str(r[k])
                for k in ("topic", "day", "judge", "prob")
                if r.get(k) not in (None, "")
            }
            items.append(
                Item(
                    str(r.get("request_id") or r["case_id"]),
                    r["trace_id"],
                    list(r.get("reasons", [])),
                    list(r.get("duplicates", [])),
                    ctx,
                )
            )
    missing = [it.trace_id for it in items if it.trace_id not in traces]
    if missing:
        raise ValueError(
            f"{len(missing)} queue items have no trace in the trace file, e.g. {missing[0]}"
        )
    return items


class Workspace:
    """Everything the app reads and writes. Labels: <out_dir>/labels-<annotator>.csv;
    golden flags: <out_dir>/golden-<annotator>.json; modes added during review:
    <out_dir>/modes-added.toml."""

    def __init__(
        self,
        traces: Path,
        queue: Path | None,
        modes: Path,
        out_dir: Path,
        extra_labels: dict[str, Path] | None = None,
    ):
        self.traces = load_spans(traces)
        self.queue = load_queue(queue, self.traces)
        self.position = {it.case_id: i for i, it in enumerate(self.queue)}
        self.base_modes = load_modes(modes)
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.extra_labels = dict(extra_labels or {})

    # modes
    @property
    def added_path(self) -> Path:
        return self.out_dir / "modes-added.toml"

    def added_modes(self) -> dict[str, FailureMode]:
        if not self.added_path.exists():
            return {}
        data = tomllib.loads(self.added_path.read_text(encoding="utf-8"))
        return {
            m["id"]: FailureMode(
                m["id"], m.get("name", m["id"]), m.get("definition", ""), int(m.get("severity", 2))
            )
            for m in data.get("mode", [])
        }

    def modes(self) -> dict[str, FailureMode]:
        return {**self.base_modes, **self.added_modes()}

    def add_mode(self, mode_id: str, definition: str) -> None:
        if not MODE_RE.match(mode_id):
            raise ValueError(
                "a mode id is lowercase words joined by hyphens, like unknown-device-guess"
            )
        if mode_id in self.modes():
            return
        definition = definition.replace("\\", " ").replace('"', "'").replace("\n", " ").strip()
        with self.added_path.open("a", encoding="utf-8") as fh:
            fh.write(
                f'\n[[mode]]\nid = "{mode_id}"\nname = "{mode_id}"\n'
                f'definition = "{definition or "added during review"}"\nseverity = 2\n'
            )

    # labels
    def labels_path(self, annotator: str) -> Path:
        if not valid_name(annotator):
            raise ValueError(f"invalid annotator name {annotator!r}")
        return self.out_dir / f"labels-{annotator}.csv"

    def flags_path(self, annotator: str) -> Path:
        if not valid_name(annotator):
            raise ValueError(f"invalid annotator name {annotator!r}")
        return self.out_dir / f"golden-{annotator}.json"

    def annotators(self) -> list[str]:
        own = sorted(p.stem.removeprefix("labels-") for p in self.out_dir.glob("labels-*.csv"))
        return own + sorted(n for n in self.extra_labels if n not in own)

    def labels(self, annotator: str) -> dict[str, Annotation]:
        path = self.extra_labels.get(annotator) or self.labels_path(annotator)
        return {a.case_id: a for a in load_annotations(path)}

    def flags(self, annotator: str) -> set[str]:
        p = self.flags_path(annotator)
        return set(json.loads(p.read_text())) if p.exists() else set()

    def save(self, annotator: str, ann: Annotation, golden: bool) -> None:
        if annotator in self.extra_labels:
            raise ValueError(f"{annotator} is a read-only label file")
        ann.annotator = annotator
        ann.annotated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        rows = self.labels(annotator) if self.labels_path(annotator).exists() else {}
        rows[ann.case_id] = ann
        order = {it.case_id: i for i, it in enumerate(self.queue)}
        save_annotations(
            self.labels_path(annotator),
            sorted(rows.values(), key=lambda a: order.get(a.case_id, len(order))),
        )
        flags = self.flags(annotator)
        (flags.add if golden else flags.discard)(ann.case_id)
        self.flags_path(annotator).write_text(json.dumps(sorted(flags)) + "\n")

    def next_unlabelled(self, annotator: str, after: int = -1) -> int | None:
        done = self.labels(annotator) if annotator else {}
        n = len(self.queue)
        for k in range(1, n + 1):
            i = (after + k) % n
            if self.queue[i].case_id not in done:
                return i
        return None
