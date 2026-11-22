"""Code-based checks: the cheapest, most reliable evaluators you will ever write.

A check is a named function from (case, output) to bool. Module 1 uses three of them;
module 5 adds LLM judges next to these, never instead of them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

CheckFn = Callable[[dict[str, Any], str], bool]


@dataclass(frozen=True)
class Check:
    name: str
    fn: CheckFn
    description: str = ""


@dataclass(frozen=True)
class CheckResult:
    case_id: str
    check: str
    passed: bool


def run_checks(
    cases: Iterable[dict[str, Any]], outputs: dict[str, str], checks: list[Check]
) -> list[CheckResult]:
    results = []
    for case in cases:
        out = outputs[case["id"]]
        for chk in checks:
            results.append(CheckResult(case["id"], chk.name, bool(chk.fn(case, out))))
    return results


def summarize(results: list[CheckResult]) -> dict[str, Any]:
    """Per-check pass counts plus the number of cases that pass every check."""
    by_check: dict[str, list[bool]] = {}
    by_case: dict[str, list[bool]] = {}
    for r in results:
        by_check.setdefault(r.check, []).append(r.passed)
        by_case.setdefault(r.case_id, []).append(r.passed)
    return {
        "checks": {k: (sum(v), len(v)) for k, v in by_check.items()},
        "all_pass": (sum(all(v) for v in by_case.values()), len(by_case)),
        "failing_cases": sorted(c for c, v in by_case.items() if not all(v)),
    }
