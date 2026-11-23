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

Record and live mode call one model only: `[live].model` in `config/models.toml`, set to `claude-haiku-4-5`. Every
request is sent to it whatever its role, with that model's own settings, and any other model is refused before the
request is sent. Recordings are keyed with that model, so replay them with `EVALS_REPLAY_LIVE_MODEL=1`. Module 12's
[Make it your own](modules/12-capstone/extensions.md) lists what that changes.

Model choices live in `config/models.toml`: a stronger model for the agent and a cheaper one for judges and
synthetic data.
