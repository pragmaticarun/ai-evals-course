"""Command line: `annotate serve ...` starts the app; `annotate kappa A.csv B.csv` compares labels."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evalkit.annotate import kappa_report, load_annotations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="annotate", description="Keyboard-driven trace review.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("serve", help="start the review app on 127.0.0.1")
    sp.add_argument("--traces", type=Path, required=True, help="spans as JSONL (evalkit.trace)")
    sp.add_argument("--queue", type=Path, help="queue JSONL (default: every trace in file order)")
    sp.add_argument("--modes", type=Path, required=True, help="failure modes TOML")
    sp.add_argument("--out", type=Path, required=True, help="directory for labels and exports")
    sp.add_argument("--dashboard", type=Path, help="monitoring summary JSON to show at /dashboard")
    sp.add_argument(
        "--compare",
        action="append",
        default=[],
        metavar="NAME=CSV",
        help="read-only labels to compare with",
    )
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8009)
    sp = sub.add_parser("kappa", help="Cohen's kappa between two label CSVs")
    sp.add_argument("left", type=Path)
    sp.add_argument("right", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        from annotate.app import Config, serve

        compare = dict(c.split("=", 1) for c in a.compare)
        serve(
            Config(
                a.traces,
                a.modes,
                a.out,
                a.queue,
                a.dashboard,
                {k: Path(v) for k, v in compare.items()},
            ),
            a.host,
            a.port,
        )
    else:
        rep = kappa_report(
            load_annotations(a.left), load_annotations(a.right), a.left.stem, a.right.stem
        )
        print(
            f"{len(rep.common)} common cases; agreement {rep.observed:.2f}; Cohen's kappa {rep.kappa:.2f}"
        )
        for m, (k, both, lo, ro) in rep.per_mode.items():
            print(
                f"  {m:28} kappa {k:5.2f}  both {both}  only {rep.left} {lo}  only {rep.right} {ro}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
