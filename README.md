# AI Evals, Hands-On

An original, self-paced course on evaluating LLM agents. You build one running agent, **MediaDoctor**
(Android and multimedia debugging assistant on Claude), and take it through the whole loop: analyze failures,
measure them with evaluators you trust, and improve with evidence.

Site: https://pragmaticarun.github.io/ai-evals-course/

## Quick start

```bash
uv sync                                   # Python 3.14 + pinned deps from uv.lock
uv run pytest -q                          # offline: replays recorded Claude responses
uv run mediadoctor-lab01 compare v1 v2    # the module 1 worked example
uv run mediadoctor-lab02 run --out runs/t.jsonl   # module 2: tool-using agent, traced
uv run evalkit view runs/t.jsonl m2q03    # read one trace in the terminal
uv run mediadoctor-lab03 rank             # module 3: ranked failure modes from the reference labels
uv run mediadoctor-lab03 annotate --labels runs/m3_labels.csv   # label the 100 traces yourself
uv run mediadoctor-lab04 generate --out runs/m4_v1.jsonl   # module 4: tuples -> synthetic queries -> dataset v1
uv run mediadoctor-lab04 coverage         # coverage matrix of the frozen dataset
uv run mediadoctor-lab05 validate --split dev   # module 5: LLM judges vs human labels (TPR/TNR)
uv run mediadoctor-lab05 estimate         # judge-corrected pass rate with a bootstrap CI
uv run mediadoctor-lab06 modes            # module 6: prompt v1 vs v2 per failure mode, paired tests
uv run mediadoctor-lab06 report --out runs/m6_report.md   # metric report with confidence intervals
uv run mediadoctor-lab07 retrieval        # module 7: recall@k, MRR, nDCG for 4 chunking/ranking configs
uv run mediadoctor-lab07 agents           # planner + specialists: transition-failure matrix
uv run mediadoctor-lab07 report --out runs/m7_report.md   # RAG, multi-turn, multi-agent, and vision evals
uv run pytest evals -m "not judges"       # module 8: the eval suite's fast tier (the judge tier: -m judges)
uv run mediadoctor-lab08 gate --prompt v2 # the regression gate on a prompt change (blocked: exit 1)
uv run mediadoctor-lab08 hygiene          # leakage, contamination, and stale-label checks on the golden set
uv run zensical serve                     # the course site at http://localhost:8000
```

No API key is needed for any of the above. To record real responses, set `ANTHROPIC_API_KEY` in your
environment (or a git-ignored `.env`) and use `EVALS_LLM_MODE=record`. See `docs/setup.md`.

## Layout

```text
config/models.toml        Claude model per role (agent; cheaper judge and synth)
config/synth/             test dimensions and exclusion rules for synthetic data (module 4)
config/judges/            versioned LLM judge specs: criterion, PASS/FAIL, context, train-split examples (module 5)
config/release.toml       the prompt MediaDoctor ships; the eval gate compares changes to it (module 8)
config/eval_gate.toml     the eval gate's tiers, rule, and budgets (module 8)
docs/                     course site (Zensical, Material-compatible mkdocs.yml)
labs/evalkit/             record/replay LLM wrapper, fixtures, tracer, trace viewer, OTLP export, annotation and taxonomy tools, synthetic data (tuples, batching, dedup, coverage, splits), judges (prompts, TPR/TNR), statistics (Wilson and bootstrap CIs, judge-error correction, McNemar, Holm, pass^k, sample sizes), retrieval metrics, trajectory metrics and transition-failure matrices, regression gates, golden manifests, dataset hygiene
labs/mediadoctor/         the running agent (module 1 seed; module 2 Claude tool-use agent with 4 tools; module 7 RAG, chat with a simulated user, planner + specialists, vision)
data/kb/                  knowledge-base notes the agent retrieves from
data/kb_v2/               second-edition knowledge base (25 docs, 57 sections) for the module 7 retrieval evals
data/sessions/            multi-turn chat scenarios for the simulated user (module 7)
data/datasets/            versioned case sets (module03_cases.jsonl: 100-trace error-analysis set; module04_v1.jsonl: synthetic dataset v1 + manifest)
data/synth/               stand-in "beta" queries used as style examples and seeds (synthetic-authored)
data/labels/              reference annotations and failure-mode definitions (synthetic-authored)
data/golden/              the golden set's manifest, labelled-answer digests, hygiene review (module 8)
data/media/               small ffmpeg-generated sample clips + cached ffprobe output; frames/ has module 7's test frames and spectrograms
data/devices/, data/logs/ fictional device codec tables and synthetic logcat captures
fixtures/recorded/        SHA-256 keyed JSONL recorded responses (replayed in CI)
scripts/                  maintenance scripts (fixture authoring, version report)
tests/                    pytest suite, offline
evals/                    the eval suite as pytest tests (fast and judge tiers) and the committed baseline (module 8)
.github/workflows/        ci.yml, deploy.yml (GitHub Pages), eval-gate.yml (module 8 gate), live-evals.yml (manual)
```

## Licenses

Content (`docs/`, `data/`, `fixtures/`) is CC BY 4.0 (`LICENSE-CONTENT`); code is MIT (`LICENSE`).

## Credits

Inspired by Hamel Husain and Shreya Shankar's work on AI evals. See `docs/credits.md`. This course is
independent and not affiliated with them, Maven, or Anthropic.
