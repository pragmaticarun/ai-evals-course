#!/usr/bin/env bash
# Every command whose model calls, together, read every fixture record (checked in audit mode).
# Run from the repo root with SUBAGENT_HARNESS_DIR and PYTHONPATH=scripts/subagent_harness set.
# Exit codes are ignored: in collect mode, placeholder answers make checks fail on purpose.
set -u
q() { "$@" </dev/null >/dev/null 2>&1 || true; }
q uv run pytest -q -p no:cacheprovider -x --co   # import check only
q uv run pytest -q -p no:cacheprovider
q uv run mediadoctor-capstone run
for v in v1 v2 v3 v3-cache haiku cascade retry; do
  q uv run mediadoctor-lab11 run "$v"
  q uv run mediadoctor-lab11 confirm "$v" --release
  q uv run mediadoctor-lab11 latency "$v"
done
q uv run mediadoctor-lab11 cost --runs 5
q uv run mediadoctor-lab11 report
for g in none v1 v2; do
  q uv run mediadoctor-lab10 run --guard "$g"
  q uv run mediadoctor-lab10 trace wx01 --guard "$g"
  q uv run mediadoctor-lab10 trace wx02 --guard "$g"
done
for a in reviewer approve deny ask; do q uv run mediadoctor-lab10 hitl --approver "$a"; done
q uv run mediadoctor-lab07 agents
for c in $(tail -n +2 data/labels/module07_agents.csv | cut -d, -f1); do q uv run mediadoctor-lab07 run "$c"; done
