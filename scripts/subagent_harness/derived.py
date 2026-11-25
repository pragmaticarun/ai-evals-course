"""Regenerate the files the course derives from fixtures and reference labels.

    uv run python scripts/subagent_harness/derived.py

Runs, in order, the same code the author scripts use for these steps (without re-recording any
model output): module 6's reference answers, module 9's simulated week of traffic, module 8's
golden label answers, manifest and gate baseline, and module 10's red-team baseline.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from author_module08_fixtures import CREATED, write_manifest  # noqa: E402
from author_module09_fixtures import write_traffic  # noqa: E402
from module03_scenarios import S  # noqa: E402

from mediadoctor import lab04, lab05, lab06, lab08, lab09  # noqa: E402

L, N = "Likely cause:", "Next step:"


def module06_references() -> None:
    rows = lab05.label_rows()
    with lab06.references_path().open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["case_id", "reference"])
        w.writeheader()
        for r in rows:
            sc = S[lab04.scenario_for(r)]
            w.writerow({"case_id": r["id"], "reference": f"{L} {sc['cause']}\n{N} {sc['next']}"})
    print(f"module 6 reference answers: {len(rows)}")


def module09_traffic() -> None:
    behs = {c["id"]: "" for c in lab09.drift_cases()}  # only the ids are used (vela-v2 vs others)
    print(f"module 9 traffic: {write_traffic(behs)} requests")


def module08() -> None:
    print("wrote", lab08.rel(lab08.write_label_answers()))
    print("wrote", lab08.rel(write_manifest(lab08.manifest_path(), lab08.make_manifest(created=CREATED))))
    print("wrote", lab08.rel(lab08.write_baseline()))


def module10() -> None:
    subprocess.run(["uv", "run", "mediadoctor-lab10", "gate", "--write-baseline"], check=True, cwd=ROOT)


if __name__ == "__main__":
    steps = sys.argv[1:] or ["module06_references", "module09_traffic", "module08", "module10"]
    for s in steps:
        globals()[s]()
