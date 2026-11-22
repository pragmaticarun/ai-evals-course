"""Load model roles from config/models.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


def repo_root(start: Path | None = None) -> Path:
    """Find the course repo root (the directory holding config/models.toml).

    Honors EVALS_REPO_ROOT if set, otherwise walks up from `start` (or the CWD).
    """
    env = os.environ.get("EVALS_REPO_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "config" / "models.toml").is_file():
            return candidate
    # Fall back to the location of this file inside labs/evalkit/src/evalkit/
    pkg_guess = Path(__file__).resolve().parents[4]
    if (pkg_guess / "config" / "models.toml").is_file():
        return pkg_guess
    raise FileNotFoundError("Could not find config/models.toml; set EVALS_REPO_ROOT.")


@dataclass(frozen=True)
class ModelRole:
    name: str
    model: str
    max_tokens: int


def load_models(path: Path | None = None) -> dict[str, ModelRole]:
    path = path or repo_root() / "config" / "models.toml"
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    roles = {}
    for name, cfg in raw.items():
        roles[name] = ModelRole(
            name=name, model=str(cfg["model"]), max_tokens=int(cfg["max_tokens"])
        )
    return roles
