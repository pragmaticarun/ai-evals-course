"""Re-key every recorded fixture after a change to `[generation.<model>]` in config/models.toml.

    uv run python scripts/migrate_fixtures_generation.py [--check]

evalkit.LLM fills each model's generation settings (thinking, effort) into every request before
keying it, so a change to those settings changes every key. Each fixture stores its request in
full, so this script applies the same fill (`evalkit.config.apply_generation`) to the stored
request and recomputes the key with the record's own trial number. Responses, latencies, and
sources are untouched: nothing is re-recorded or rewritten except the request and its key.

This is only sound for synthetic-authored records, or for a change that does not alter what the
model would have answered. Records from a real API call (`"source": "live"`) answered the old
request, so the script refuses to move them; re-record those instead.

With --check, exit 1 if any record would change (used by tests to keep fixtures in step).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evalkit.config import apply_generation, repo_root
from evalkit.fixtures import canonical_json, request_key


def migrate_file(path: Path) -> tuple[list[str], int]:
    lines, changed = [], 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        rec = json.loads(raw)
        request = apply_generation(rec["request"])
        key = request_key(request, rec.get("trial", 0))
        if key != rec["request_sha256"] or request != rec["request"]:
            if rec.get("source") != "synthetic-authored":
                raise SystemExit(
                    f"{path.name}: {rec['request_sha256'][:12]} is a {rec.get('source')!r} "
                    "record; re-record it instead of re-keying it"
                )
            rec = {**rec, "request": request, "request_sha256": key}
            changed += 1
        lines.append(canonical_json(rec))
    return lines, changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check", action="store_true", help="report only; exit 1 if anything would change"
    )
    args = ap.parse_args(argv)
    total = 0
    for path in sorted((repo_root() / "fixtures" / "recorded").glob("*.jsonl")):
        lines, changed = migrate_file(path)
        total += changed
        if changed and not args.check:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if changed:
            print(
                f"{path.name}: {changed} record(s) {'would change' if args.check else 're-keyed'}"
            )
    print(f"{total} record(s) {'out of step' if args.check else 're-keyed'}")
    return 1 if (args.check and total) else 0


if __name__ == "__main__":
    sys.exit(main())
