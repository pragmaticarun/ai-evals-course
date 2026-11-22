"""Module 1 lab: run the seed agent over 20 queries, apply three code checks, compare prompts.

    uv run mediadoctor-lab01 run --prompt v1
    uv run mediadoctor-lab01 compare v1 v2
    uv run mediadoctor-lab01 show q05 --prompt v1

Runs in replay mode by default (no API key, no network). Set EVALS_LLM_MODE=record to
re-record against the real Anthropic API.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from evalkit import LLM, Check, repo_root, run_checks, summarize
from mediadoctor.agent import AGENT_NAMESPACE, answer
from mediadoctor.kb import load_kb

MAX_WORDS = 120
CITE_RE = re.compile(r"\[kb:([a-z0-9\-]+)\]")


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or repo_root() / "data" / "datasets" / "module01_queries.jsonl"
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --- The three code checks used in the lab -------------------------------------------


def has_format(case: dict, output: str) -> bool:
    """Every answer must contain the three labelled lines, in order."""
    pos = [output.find(label) for label in ("Likely cause:", "Next step:", "Sources:")]
    return all(p >= 0 for p in pos) and pos == sorted(pos)


def cites_known_doc(case: dict, output: str, _kb_ids: set[str] | None = None) -> bool:
    """At least one [kb:<id>] citation, and every cited id exists in the knowledge base."""
    kb_ids = _kb_ids if _kb_ids is not None else set(load_kb().docs)
    cited = CITE_RE.findall(output)
    return bool(cited) and all(c in kb_ids for c in cited)


def within_length(case: dict, output: str) -> bool:
    return len(output.split()) <= MAX_WORDS


def default_checks() -> list[Check]:
    kb_ids = set(load_kb().docs)
    return [
        Check("format", has_format, "Has Likely cause / Next step / Sources, in order"),
        Check(
            "cites_kb", lambda c, o: cites_known_doc(c, o, kb_ids), "Cites at least one real KB doc"
        ),
        Check("length", within_length, f"At most {MAX_WORDS} words"),
    ]


# --- Running -----------------------------------------------------------------------------


def run_prompt(prompt_version: str, llm: LLM | None = None) -> dict[str, str]:
    llm = llm or LLM(namespace=AGENT_NAMESPACE)
    kb = load_kb()
    return {c["id"]: answer(c["query"], prompt_version, llm=llm, kb=kb) for c in load_cases()}


def evaluate(prompt_version: str, llm: LLM | None = None) -> dict[str, Any]:
    cases = load_cases()
    outputs = run_prompt(prompt_version, llm)
    results = run_checks(cases, outputs, default_checks())
    return {"outputs": outputs, "results": results, "summary": summarize(results)}


def _print_summary(label: str, summary: dict[str, Any]) -> None:
    print(f"\n== prompt {label} ==")
    for name, (passed, total) in summary["checks"].items():
        print(f"  {name:<10} {passed:>2}/{total}")
    p, t = summary["all_pass"]
    print(f"  {'ALL':<10} {p:>2}/{t}   failing: {', '.join(summary['failing_cases']) or 'none'}")


def cmd_run(args: argparse.Namespace) -> int:
    ev = evaluate(args.prompt)
    by_case: dict[str, list[str]] = {}
    for r in ev["results"]:
        if not r.passed:
            by_case.setdefault(r.case_id, []).append(r.check)
    for cid in sorted(ev["outputs"]):
        status = "PASS" if cid not in by_case else "FAIL " + ",".join(by_case[cid])
        print(f"{cid}  {status}")
    _print_summary(args.prompt, ev["summary"])
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for cid, text in sorted(ev["outputs"].items()):
                fh.write(json.dumps({"id": cid, "prompt": args.prompt, "output": text}) + "\n")
        print(f"\nwrote {out}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    a, b = evaluate(args.a), evaluate(args.b)
    _print_summary(args.a, a["summary"])
    _print_summary(args.b, b["summary"])
    fa, fb = set(a["summary"]["failing_cases"]), set(b["summary"]["failing_cases"])
    print(f"\nfixed by {args.b}:  {', '.join(sorted(fa - fb)) or 'none'}")
    print(f"broken by {args.b}: {', '.join(sorted(fb - fa)) or 'none'}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    case = next((c for c in load_cases() if c["id"] == args.case_id), None)
    if case is None:
        print(f"unknown case {args.case_id}", file=sys.stderr)
        return 2
    print(f"Q: {case['query']}\n")
    print(answer(case["query"], args.prompt))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mediadoctor-lab01", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="run all 20 queries and the three checks")
    p_run.add_argument("--prompt", default="v1", choices=["v1", "v2"])
    p_run.add_argument("--out", help="write outputs as JSONL (e.g. runs/v1.jsonl)")
    p_run.set_defaults(func=cmd_run)
    p_cmp = sub.add_parser("compare", help="compare two prompt versions case by case")
    p_cmp.add_argument("a", choices=["v1", "v2"])
    p_cmp.add_argument("b", choices=["v1", "v2"])
    p_cmp.set_defaults(func=cmd_compare)
    p_show = sub.add_parser("show", help="print one answer")
    p_show.add_argument("case_id")
    p_show.add_argument("--prompt", default="v1", choices=["v1", "v2"])
    p_show.set_defaults(func=cmd_show)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
