"""Trajectory evaluation for multi-step and multi-agent systems (module 7).

A trajectory is the ordered list of steps an agent took: tool calls with arguments, handoffs
between agents, and the final answer. Evaluate it in two layers:

1. The outcome: did the final state meet the goal? (Always first.)
2. The steps: right tools, right arguments, sensible order, no wasted steps, and, when the outcome
   failed, where the first failure happened.

    tool_recall / tool_precision   expected tools called / called tools expected (sets)
    in_order                       expected steps appear as a subsequence of the actual ones
    step_efficiency                minimal steps / steps taken (1.0 = no wasted steps)
    first_failure                  (last successful state, first failed state) for one run
    transition_matrix              counts of those pairs over many runs
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence

START = "start"


def tool_recall(expected: Iterable[str], actual: Iterable[str]) -> float:
    exp = set(expected)
    return len(exp & set(actual)) / len(exp) if exp else 1.0


def tool_precision(expected: Iterable[str], actual: Iterable[str]) -> float:
    act = set(actual)
    return len(act & set(expected)) / len(act) if act else 1.0


def in_order(expected: Sequence[str], actual: Sequence[str]) -> bool:
    """True if `expected` is a subsequence of `actual` (extra steps in between are allowed)."""
    it = iter(actual)
    return all(any(a == e for a in it) for e in expected)


def step_efficiency(minimal: int, taken: int) -> float:
    if taken <= 0:
        return 0.0
    return min(1.0, minimal / taken)


def first_failure(states: Sequence[str], ok: Callable[[int, str], bool]) -> tuple[str, str] | None:
    """Walk the states in order; return (last successful state, first failed state), or None if
    every state succeeded. `ok(i, state)` decides whether step i succeeded."""
    last = START
    for i, s in enumerate(states):
        if not ok(i, s):
            return last, s
        last = s
    return None


def transition_matrix(
    failures: Iterable[tuple[str, str] | None],
) -> tuple[list[str], list[str], dict[tuple[str, str], int]]:
    """Rows: last successful state. Columns: first failed state. Successful runs are skipped."""
    counts = Counter(f for f in failures if f is not None)
    rows = sorted({r for r, _ in counts}, key=lambda s: (s != START, s))
    cols = sorted({c for _, c in counts})
    return rows, cols, dict(counts)


def format_matrix(
    rows: list[str], cols: list[str], counts: dict[tuple[str, str], int], width: int = 11
) -> str:
    head = "last ok \\ failed".ljust(18) + "".join(c[:width].rjust(width + 1) for c in cols)
    lines = [head]
    for r in rows:
        cells = "".join(str(counts.get((r, c)) or ".").rjust(width + 1) for c in cols)
        lines.append(r[:18].ljust(18) + cells)
    return "\n".join(lines)
