# Lab 8: An eval gate in CI (offline)

**Time:** about 3 hours. **Needs:** the setup from [lab 1](../01-why-evals/lab.md), modules 5 and 6, and a GitHub
fork of the course repo if you want to watch the workflow run. **Does not need:** an API key.

You will run the eval suite as pytest tests, gate the v1 to v2 prompt change from module 6 against a committed
baseline, read the comparison report, watch the gate fail on a deliberately regressing branch, check the golden
dataset's manifest and hygiene, look at the held-out split the right way, and price the tiers. Keep your own files
under `runs/`, which git ignores.

!!! info "Synthetic-authored fixtures"
    The agent runs are module 5's (prompt v1) and module 6's (prompt v2), and so are their labels. The judge
    verdicts on v2's dev-split answers that module 5 had not already recorded (54 of them) were written for this
    module by `scripts/author_module08_fixtures.py`: the verdict is module 6's reference label, with module 5's
    documented judge-error patterns. Records are labelled `"source": "synthetic-authored"`. The gate, the reports,
    the manifest, and the hygiene results are computed, not authored.

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q tests/test_gate.py tests/test_golden.py tests/test_hygiene.py tests/test_lab08.py
```

New files to skim:

- `labs/evalkit/src/evalkit/gate.py`: the gate rule, flips, budgets;
- `labs/evalkit/src/evalkit/golden.py`: manifests, the held-out guard, rotation;
- `labs/evalkit/src/evalkit/hygiene.py`: cross-split pairs, n-gram contamination, stale labels;
- `labs/mediadoctor/src/mediadoctor/lab08.py`: the suite, the report, and the CLI;
- `evals/`: the eval suite as pytest tests;
- `config/release.toml` and `config/eval_gate.toml`: what ships, and the gate's rules and budgets;
- `.github/workflows/eval-gate.yml`: the workflow.

## 2. The suite as pytest tests

```bash
uv run pytest evals -m "not judges" -v     # fast tier: 11 tests
uv run pytest evals -m judges -v           # judge tier: 5 tests
```

The fast tier's tests are named for what they protect:

```text
evals/test_gate_code.py::test_no_regression[format] PASSED
evals/test_gate_code.py::test_no_regression[citations] PASSED
evals/test_gate_code.py::test_no_regression[investigated] PASSED
evals/test_gate_code.py::test_no_regression[all-code-checks] PASSED
evals/test_gate_code.py::test_code_tier_within_budget PASSED
evals/test_golden.py::test_manifest_matches_the_files PASSED
evals/test_golden.py::test_splits_do_not_overlap PASSED
evals/test_golden.py::test_gate_tiers_never_read_the_holdout PASSED
evals/test_golden.py::test_no_leakage_or_unreviewed_contamination_or_stale_labels PASSED
evals/test_replay.py::test_release_config_is_recorded PASSED
evals/test_replay.py::test_committed_baseline_describes_this_commit PASSED
```

Open `evals/conftest.py`. The `head_code` and `head_judges` fixtures replay the release configuration once per
session; `base` loads the baseline from the git ref in `EVAL_GATE_BASE_REF`, or from this checkout if it is unset.

## 3. Preflight: is everything recorded?

```bash
uv run mediadoctor-lab08 preflight
uv run mediadoctor-lab08 preflight --prompt v2
```

Both report `108/108 first requests recorded`, with the configuration's fingerprint (`371cb022dc79` for v1,
`7647f3451627` for v2). The fingerprint hashes the model, limits, system prompt, and tool definitions: anything that
changes it changes every request key.

## 4. Two runs and their diff

```bash
uv run mediadoctor-lab08 run --prompt v1 --tier all --out runs/v1.json
uv run mediadoctor-lab08 run --prompt v2 --tier all --out runs/v2.json
uv run mediadoctor-lab08 diff runs/v1.json runs/v2.json --out runs/m8_diff.md
```

Each JSON file holds, per tier and metric, every case's outcome, a digest of every answer, and the run's usage.
Open `runs/m8_diff.md` (a Markdown preview renders it as it will look on GitHub). Find: the two failing metrics, the 16
format flips and what their answers start with, why tool-grounding's n is 33 rather than 37 (the judge does not apply
where no tool succeeded on one side), and the two judges that warn.

## 5. The gate and the job summary

```bash
uv run mediadoctor-lab08 gate --summary runs/summary.md            # the release config vs the baseline
echo "exit $?"
uv run mediadoctor-lab08 gate --prompt v2 --tier all --out runs/gate_v2.md
echo "exit $?"
```

The first passes (exit 0) with "Same configuration on both sides". The second exits 1, blocked. `--summary` appends
to a file, which is exactly what GitHub does with `$GITHUB_STEP_SUMMARY`: whatever Markdown a step appends appears
on the run's summary page. Exit codes: 0 pass (or warn), 1 blocked, 3 replay misses.

## 6. Watch the gate fail on a regressing branch

Do this in a separate worktree so your checkout stays clean. First commit or stash your own changes; the gate reads
the baseline from `main` with `git show`.

```bash
git worktree add -b try-v2 ../try-v2 main
cd ../try-v2
uv sync
sed -i 's/^prompt = "v1"/prompt = "v2"/' config/release.toml      # ship v2
uv run mediadoctor-lab08 baseline --check                         # stale: the PR must commit a new baseline
uv run mediadoctor-lab08 baseline --write
git commit -qam "Ship prompt v2"
git diff main --stat                                              # release.toml and 105 changed baseline lines
EVAL_GATE_BASE_REF=main uv run pytest evals -m "not judges" -q    # 2 failed, 9 passed
uv run mediadoctor-lab08 gate --base-ref main --out ../try-v2-gate.md; echo "exit $?"   # exit 1
```

The pytest failure names the metric and the evidence:

```text
FAILED evals/test_gate_code.py::test_no_regression[format] - AssertionError: ...
FAILED evals/test_gate_code.py::test_no_regression[all-code-checks] - AssertionError: ...
E       AssertionError: all-code-checks: -0.157 [-0.231, -0.093], p(adj.)=<0.001: worse, and not by chance
```

Now try the fix from the worked example. In `labs/mediadoctor/src/mediadoctor/toolagent.py`, add this sentence to
the end of v2's paragraph about user claims: `Say it inside "Likely cause"; never add a line before it.` Then:

```bash
uv run mediadoctor-lab08 preflight          # 0/108 first requests recorded, and a new fingerprint
uv run mediadoctor-lab08 gate --base-ref main; echo "exit $?"   # exit 3: needs re-recorded fixtures
```

Clean up when you are done:

```bash
cd -
git worktree remove --force ../try-v2 && git branch -D try-v2
```

## 7. The workflow

Read `.github/workflows/eval-gate.yml`:

- **Triggers.** `pull_request` and pushes to `main` run the `code-gate` job. The `judge-gate` job runs on the nightly
  schedule (21:45 UTC, 03:15 IST), on `workflow_dispatch`, and on pull requests that carry a `run-judges` label. To
  use the label, create it once in your fork (Issues, Labels); the workflow works without it.
- **Base.** For a PR the base is `github.event.pull_request.base.sha`; for a push, `github.event.before`. If that
  commit is missing (a new branch, a force push) the job falls back to `HEAD`. `fetch-depth: 0` makes `git show`
  possible. Values from the event are passed through `env:`, never pasted into the script.
- **Steps.** Pytest runs the tier; then the gate step runs `if: always()`, so the summary and the artifact exist
  even when a test failed.
- **Budget guards.** `timeout-minutes`, a concurrency group that cancels superseded runs (a label event has its own
  group, so labelling a PR does not cancel its code tier), uv caching, and `EVALS_LLM_MODE: replay` for the whole
  workflow.
- **Permissions.** `contents: read` only. The workflow posts nothing to the PR; the summary and the artifact are
  enough, and they need no write token.

If you have a fork, push a branch and open a PR against your own fork's `main` to see the summary page. The course
repo itself does this on every push to `main`.

## 8. The golden manifest and hygiene

```bash
uv run mediadoctor-lab08 manifest --check
uv run mediadoctor-lab08 hygiene
```

The manifest check reports `mediadoctor-golden 1.0.0: 12 files and 3 splits match`. Change one character in
`data/labels/module06_runs.csv` and run it again; then `git checkout data/labels/` to undo it.

Hygiene prints the three closest gate and held-out questions (the closest scores 0.344, just under module 4's
grouping threshold of 0.35), no exact duplicates, no judge-example leaks, no stale labels, and five reviewed
contamination findings from `data/golden/hygiene_review.csv`. Read the five questions next to the judge examples
they overlap (`uv run mediadoctor-lab05 show false-premise` prints that judge's prompt, examples included) and decide
whether you agree with the decisions.

## 9. The held-out split, the right way

```bash
uv run mediadoctor-lab08 release                  # the release prompt on the 29 held-out cases
uv run mediadoctor-lab08 release --prompt v2      # the candidate
```

v1 passes all code checks on 0.931 of the held-out cases; v2 on 0.862. Add `--log --note "v2 release review"` to
record a look in `data/golden/holdout_log.csv` (then decide whether to commit it: on a real team you would). Read
`rotate` in `evalkit/golden.py`, and write down the rotation rule you would use.

## 10. Budgets

```bash
uv run mediadoctor-lab08 budget
```

```text
code    replay  0.18 s | live re-record: 238 calls, 202,666 in / 14,256 out tokens, $0.55, 1.4 min at 4 parallel
judges  replay  0.29 s | live re-record: 191 calls, 323,118 in / 9,553 out tokens, $0.22, 1.0 min at 4 parallel
```

Compare them with `[budget]` in `config/eval_gate.toml`. Which number would break first if the gate set grew to
1,000 cases?

## 11. Optional: record a candidate for real

With an API key, the worked example's fix can be recorded and gated. New agent runs are written to
`fixtures/recorded/mediadoctor-m8-agent.jsonl`, new judge verdicts to `mediadoctor-m8-judges.jsonl`:

```bash
EVALS_LLM_MODE=record uv run mediadoctor-lab08 run --prompt v2 --tier all --out runs/v2_fix.json
uv run mediadoctor-lab08 diff evals/baseline.json runs/v2_fix.json
```

That is about 240 Sonnet calls for the code tier and about 110 Haiku calls for the judges: about $0.80 at the prices
in `config/models.toml`. Without a local key, run the manual `live-evals` workflow with the command
`mediadoctor-lab08 run --prompt v2 --tier all` and download the fixtures from its artifact. Before trusting the new
numbers, read the flips, label the changed answers, rewrite the baseline, and bump the golden manifest
(`uv run mediadoctor-lab08 manifest --write` after changing `GOLDEN_VERSION`).

## Checkpoint

- [ ] `uv run pytest evals -q` passes (16 tests), and you can say which tier each test belongs to and why
- [ ] `runs/m8_diff.md`, with a two-sentence reading of each tier
- [ ] The regressing branch: the failing tests, the gate's exit codes (1, then 3), and why each was right
- [ ] Your decision on each of the five contamination findings
- [ ] A held-out rotation rule (when, how many cases, what moves where)
- [ ] Which budget breaks first at 1,000 cases, and what you would change
