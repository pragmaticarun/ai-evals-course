"""Load model roles and prices from config/models.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


@dataclass(frozen=True)
class Price:
    input_per_mtok: float
    output_per_mtok: float

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok) / 1e6


def _load(path: Path | None) -> dict[str, Any]:
    path = path or repo_root() / "config" / "models.toml"
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_models(path: Path | None = None) -> dict[str, ModelRole]:
    raw = _load(path)
    return {
        name: ModelRole(name=name, model=str(cfg["model"]), max_tokens=int(cfg["max_tokens"]))
        for name, cfg in raw.items()
        if name != "pricing"
    }


def load_prices(path: Path | None = None) -> dict[str, Price]:
    raw = _load(path).get("pricing", {})
    return {
        model: Price(float(p["input_per_mtok"]), float(p["output_per_mtok"]))
        for model, p in raw.items()
    }
