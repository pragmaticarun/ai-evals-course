# Versions checked

Everything in this course was last installed, tested, and built on **2026-11-23** with the versions below.
Exact transitive versions are pinned in `uv.lock`. Regenerate this page with `uv run python scripts/versions_report.py`.

## Toolchain

| Tool | Version |
|---|---|
| Python | 3.14.10 (`.python-version`: 3.14) |
| uv | 0.13.8 (x86_64-unknown-linux-gnu) |
| git | 2.47.3 |
| OS used for the check | Linux x86_64 |
| gitleaks (local check) | 8.30.1 |
| actionlint (local check) | 1.7.12 |
| FFmpeg / ffprobe (sample clips and probe cache; optional) | 7.1.5-0+deb13u1 |

## Python libraries

| Package | Version | Role |
|---|---|---|
| anthropic | 2.12.0 | Anthropic Python SDK (live and record modes) |
| pytest | 9.2.0 | Test runner |
| ruff | 0.17.6 | Linter |
| zensical | 0.1.3 | Site generator (primary) |
| mkdocs | 1.6.1 | Site generator (fallback) |
| mkdocs-material | 9.8.2 | Theme for the fallback build; in maintenance mode until 2027-05-05 |
| pymdown-extensions | 13.1.2 | Markdown extensions (admonitions, details, tabs) |
| hatchling | 1.33.0 (build-time pin) | Build backend for the lab packages |

## Claude models (config/models.toml)

| Role | Model ID |
|---|---|
| agent | `claude-sonnet-5-5` |
| judge | `claude-haiku-5-5` |
| synth | `claude-haiku-5-5` |

| Model | Input $/MTok | Output $/MTok |
|---|---|---|
| `claude-sonnet-5-5` | 2.00 | 10.00 |
| `claude-haiku-5-5` | 0.10 | 0.50 |

Model IDs and prices (used for `evalkit.cost.usd` on trace spans) were checked against Anthropic's models overview (https://docs.anthropic.com/en/docs/about-claude/models/overview) and pricing page (https://docs.anthropic.com/en/docs/about-claude/pricing) on the date above.

## Specifications (module 2)

| Spec | Status when checked |
|---|---|
| OpenTelemetry GenAI semantic conventions (https://github.com/open-telemetry/semantic-conventions-genai) | Development (names may change) |
| OTLP/JSON (https://opentelemetry.io/docs/specs/otlp/) | Stable |

## GitHub Actions (major versions pinned in workflows)

| Action | Version |
|---|---|
| `actions/checkout` | `v7` |
| `astral-sh/setup-uv` | `v10.4.0 (pinned by SHA)` |
| `actions/configure-pages` | `v6` |
| `actions/upload-pages-artifact` | `v5` |
| `actions/deploy-pages` | `v5` |
| `gitleaks/gitleaks-action` | `v3` |
| `actions/upload-artifact` | `v7` |

CI tests on Python 3.14 and 3.15. Python 3.15.0 was released on 2026-10-09.
