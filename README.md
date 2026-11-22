# AI Evals, Hands-On

An original, self-paced course on evaluating LLM agents. You build one running agent, **MediaDoctor**
(Android and multimedia debugging assistant on Claude), and take it through the whole loop: analyze failures,
measure them with evaluators you trust, and improve with evidence.

Site: https://pragmaticarun.github.io/ai-evals-course/ (once published)

## Quick start

```bash
uv sync                                   # Python 3.14 + pinned deps from uv.lock
uv run pytest -q                          # offline: replays recorded Claude responses
uv run mediadoctor-lab01 compare v1 v2    # the module 1 worked example
uv run zensical serve                     # the course site at http://localhost:8000
```

No API key is needed for any of the above. To record real responses, set `ANTHROPIC_API_KEY` in your
environment (or a git-ignored `.env`) and use `EVALS_LLM_MODE=record`. See `docs/setup.md`.

## Layout

```text
config/models.toml        Claude model per role (agent; cheaper judge and synth)
docs/                     course site (Zensical, Material-compatible mkdocs.yml)
labs/evalkit/             record/replay LLM wrapper, fixture store, checks
labs/mediadoctor/         the running agent (seed version in module 1)
data/kb/                  knowledge-base notes the agent retrieves from
data/datasets/            versioned case sets
fixtures/recorded/        SHA-256 keyed JSONL recorded responses (replayed in CI)
scripts/                  maintenance scripts (fixture authoring, version report)
tests/                    pytest suite, offline
.github/workflows/        ci.yml, deploy.yml (GitHub Pages), live-evals.yml (manual)
```

## Licenses

Content (`docs/`, `data/`, `fixtures/`) is CC BY 4.0 (`LICENSE-CONTENT`); code is MIT (`LICENSE`).

## Credits

Inspired by Hamel Husain and Shreya Shankar's work on AI evals. See `docs/credits.md`. This course is
independent and not affiliated with them, Maven, or Anthropic.
