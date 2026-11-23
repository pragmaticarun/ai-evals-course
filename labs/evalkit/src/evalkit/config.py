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
    """USD per million tokens. Cache prices default to the standard multipliers of the base input
    price (5-minute cache write 1.25x, cache read 0.1x) unless config/models.toml gives them."""

    input_per_mtok: float
    output_per_mtok: float
    cache_write_per_mtok: float | None = None
    cache_read_per_mtok: float | None = None

    @property
    def cache_write(self) -> float:
        return (
            self.cache_write_per_mtok
            if self.cache_write_per_mtok is not None
            else 1.25 * self.input_per_mtok
        )  # noqa: E501

    @property
    def cache_read(self) -> float:
        return (
            self.cache_read_per_mtok
            if self.cache_read_per_mtok is not None
            else 0.1 * self.input_per_mtok
        )  # noqa: E501

    def cost_usd(
        self, input_tokens: int, output_tokens: int, cache_write_tokens: int = 0,
        cache_read_tokens: int = 0, batch: bool = False,
    ) -> float:  # fmt: skip
        """Cost of one call. `input_tokens` are the uncached input tokens (the API's
        `input_tokens`, which excludes cache writes and reads). Batch requests are 50% off."""
        usd = (
            input_tokens * self.input_per_mtok
            + output_tokens * self.output_per_mtok
            + cache_write_tokens * self.cache_write
            + cache_read_tokens * self.cache_read
        ) / 1e6
        return usd / 2 if batch else usd


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
        model: Price(
            float(p["input_per_mtok"]),
            float(p["output_per_mtok"]),
            float(p["cache_write_per_mtok"]) if "cache_write_per_mtok" in p else None,
            float(p["cache_read_per_mtok"]) if "cache_read_per_mtok" in p else None,
        )
        for model, p in raw.items()
    }
