"""Regenerate docs/versions.md from the current environment.

    uv run python scripts/versions_report.py

Records the exact tool and library versions the course was last checked with, and the date.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIBS = [
    ("anthropic", "Anthropic Python SDK (live and record modes)"),
    ("pytest", "Test runner"),
    ("ruff", "Linter"),
    ("zensical", "Site generator (primary)"),
    ("mkdocs", "Site generator (fallback)"),
    ("mkdocs-material", "Theme for the fallback build; in maintenance mode until 2027-05-05"),
    ("pymdown-extensions", "Markdown extensions (admonitions, details, tabs)"),
    ("hatchling", "Build backend for the lab packages"),
]

ACTIONS = [
    ("actions/checkout", "v7"),
    ("astral-sh/setup-uv", "v10.4.0 (pinned by SHA)"),
    ("actions/configure-pages", "v6"),
    ("actions/upload-pages-artifact", "v5"),
    ("actions/deploy-pages", "v5"),
    ("gitleaks/gitleaks-action", "v3"),
    ("actions/upload-artifact", "v7"),
]


def _cmd(*args: str) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return "not found"


def _ver(pkg: str) -> str:
    if pkg == "hatchling":  # build-time only, so read the pin instead of the environment
        text = (ROOT / "labs" / "evalkit" / "pyproject.toml").read_text()
        return text.split("hatchling==", 1)[1].split('"', 1)[0] + " (build-time pin)"
    try:
        return version(pkg)
    except Exception:
        return "not installed"


def main(checked_on: str | None = None, extra: dict[str, str] | None = None) -> None:
    checked_on = checked_on or datetime.now().astimezone().strftime("%Y-%m-%d")
    lines = [
        "# Versions checked",
        "",
        f"Everything in this course was last installed, tested, and built on **{checked_on}** with the versions below.",
        "Exact transitive versions are pinned in `uv.lock`. Regenerate this page with "
        "`uv run python scripts/versions_report.py`.",
        "",
        "## Toolchain",
        "",
        "| Tool | Version |",
        "|---|---|",
        f"| Python | {platform.python_version()} (`.python-version`: {(ROOT / '.python-version').read_text().strip()}) |",
        f"| uv | {_cmd('uv', '--version').removeprefix('uv ')} |",
        f"| git | {_cmd('git', '--version').removeprefix('git version ')} |",
        f"| OS used for the check | {platform.system()} {platform.machine()} |",
    ]
    for k, v in (extra or {}).items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Python libraries", "", "| Package | Version | Role |", "|---|---|---|"]
    lines += [f"| {p} | {_ver(p)} | {role} |" for p, role in LIBS]
    models = (ROOT / "config" / "models.toml").read_text()
    lines += [
        "",
        "## Claude models (config/models.toml)",
        "",
        "| Role | Model ID |",
        "|---|---|",
    ]
    import tomllib

    for role, cfg in tomllib.loads(models).items():
        lines.append(f"| {role} | `{cfg['model']}` |")
    lines += [
        "",
        "Model IDs were checked against Anthropic's models overview "
        "(https://docs.anthropic.com/en/docs/about-claude/models/overview) on the date above.",
        "",
        "## GitHub Actions (major versions pinned in workflows)",
        "",
        "| Action | Version |",
        "|---|---|",
    ]
    lines += [f"| `{a}` | `{v}` |" for a, v in ACTIONS]
    lines += [
        "",
        "CI tests on Python 3.14 and 3.15. Python 3.15.0 was released on 2026-10-09.",
        "",
    ]
    (ROOT / "docs" / "versions.md").write_text("\n".join(lines))
    print("wrote docs/versions.md", file=sys.stderr)


if __name__ == "__main__":
    # Optional extra tools used for the local check; reported only if present on PATH.
    extras = {}
    for tool, args in (("gitleaks", ("version",)), ("actionlint", ("-version",))):
        out = _cmd(tool, *args)
        if out != "not found":
            extras[f"{tool} (local check)"] = out.splitlines()[0]
    main(extra=extras)
