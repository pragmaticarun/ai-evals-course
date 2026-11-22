"""`evalkit` command line: view traces and convert them to OTLP/JSON.

uv run evalkit view runs/traces.jsonl                 # one line per trace
uv run evalkit view runs/traces.jsonl m2q03           # tree for one trace (case id or trace id prefix)
uv run evalkit view runs/traces.jsonl m2q03 --results # include tool results
uv run evalkit otlp runs/traces.jsonl -o runs/otlp.json [--openinference]
"""

from __future__ import annotations

import argparse
import json
import sys

from evalkit.trace import load_jsonl, to_otlp_json
from evalkit.viewer import find_trace, render_table, render_tree


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evalkit", description="evalkit trace tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("view", help="summarize traces, or show one as a tree")
    v.add_argument("file")
    v.add_argument("trace", nargs="?", help="case id or trace id prefix")
    v.add_argument("--all", action="store_true", help="show every attribute")
    v.add_argument("--results", action="store_true", help="show tool results")
    o = sub.add_parser("otlp", help="convert JSONL spans to an OTLP/JSON request body")
    o.add_argument("file")
    o.add_argument("-o", "--output", help="write here instead of stdout")
    o.add_argument("--openinference", action="store_true", help="also add OpenInference attributes")
    args = parser.parse_args(argv)

    spans = load_jsonl(args.file)
    if args.cmd == "view":
        if args.trace:
            try:
                print(render_tree(find_trace(spans, args.trace), args.all, args.results))
            except KeyError as exc:
                print(exc, file=sys.stderr)
                return 2
        else:
            print(render_table(spans))
        return 0
    body = json.dumps(to_otlp_json(spans, args.openinference), indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(body + "\n")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
