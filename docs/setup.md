# Setup

Tested on Ubuntu with the versions on [Versions checked](versions.md).

```bash
# 1. Install uv (one-time): https://docs.astral.sh/uv/getting-started/installation/
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Get the course and install everything (Python 3.14 is fetched if missing)
git clone https://github.com/pragmaticarun/ai-evals-course.git
cd ai-evals-course
uv sync

# 3. Check that it works, offline
uv run pytest -q
uv run zensical serve        # browse this site locally at http://localhost:8000
```

## Modes and API keys

| `EVALS_LLM_MODE` | Network | Key needed | Writes fixtures |
|---|---|---|---|
| `replay` (default) | No | No | No |
| `record` | Yes | Yes | Yes |
| `live` | Yes | Yes | No |

To use record or live mode, export `ANTHROPIC_API_KEY` in your shell or copy `.env.example` to `.env`
(git-ignored) and fill it in. Never commit a key; CI runs a gitleaks scan on every push.

Model choices live in `config/models.toml`: a stronger model for the agent and a cheaper one for judges and
synthetic data.
