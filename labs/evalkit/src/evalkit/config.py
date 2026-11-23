"""Load model roles and prices from config/models.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import cache
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
        if name not in ("pricing", "generation", "live")
    }


def load_generation(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Per-model request settings from `[generation.<model>]`: `thinking` and `effort`."""
    return _generation_cached(str(path) if path else "")


@cache
def _generation_cached(path: str) -> dict[str, dict[str, Any]]:
    return dict(_load(Path(path) if path else None).get("generation", {}))


def generation_params(model: str, path: Path | None = None) -> dict[str, Any]:
    """The request fields `[generation.<model>]` adds: `thinking`, and `output_config.effort`."""
    cfg = load_generation(path).get(model, {})
    params: dict[str, Any] = {}
    if "thinking" in cfg:
        params["thinking"] = dict(cfg["thinking"])
    if "effort" in cfg:
        params["output_config"] = {"effort": str(cfg["effort"])}
    return params


class ModelNotAllowedError(RuntimeError):
    """A record or live request named a model that `[live].allowed_models` does not list."""


@dataclass(frozen=True)
class LiveModel:
    model: str
    allowed: tuple[str, ...]


def load_live(path: Path | None = None) -> LiveModel | None:
    """`[live]` in config/models.toml: the one model record and live modes may call, if set."""
    raw = _load(path).get("live")
    if not raw:
        return None
    model = str(raw["model"])
    allowed = tuple(str(m) for m in raw.get("allowed_models", [model]))
    if model not in allowed:
        raise ValueError(f"[live] model {model!r} is not in its own allowed_models {list(allowed)}")
    return LiveModel(model, allowed)


def to_live_model(request: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """The request record and live modes send: `[live].model` swapped in, with that model's own
    generation settings (the role model's thinking and effort do not carry over), and refused
    unless the result names an allowed model. Without a `[live]` table, the request is unchanged
    apart from the allow check, which then does not apply."""
    live = load_live(path)
    if live is None:
        return apply_generation(request, path)
    out = {k: v for k, v in request.items() if k not in ("thinking",)}
    oc = {k: v for k, v in (out.pop("output_config", None) or {}).items() if k != "effort"}
    if oc:
        out["output_config"] = oc
    out["model"] = live.model
    out = apply_generation(out, path)
    check_live_model(out, live)
    return out


def check_live_model(request: dict[str, Any], live: LiveModel | None = None) -> None:
    """Raise ModelNotAllowedError unless the request's model is in `[live].allowed_models`."""
    live = live or load_live()
    if live is None:
        return
    model = str(request.get("model", ""))
    if model not in live.allowed:
        raise ModelNotAllowedError(
            f"refusing to call {model!r}: record and live modes may only call {list(live.allowed)} "
            "([live] in config/models.toml)"
        )


def apply_generation(request: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """A copy of `request` with the model's generation settings filled in where it sets none.

    A request that sets `thinking` keeps it; one that sets `output_config` keeps its other fields
    and gains `effort` only if it has none.
    """
    params = generation_params(str(request.get("model", "")), path)
    out = dict(request)
    if "thinking" in params and "thinking" not in out:
        out["thinking"] = params["thinking"]
    if "output_config" in params:
        oc = dict(out.get("output_config") or {})
        oc.setdefault("effort", params["output_config"]["effort"])
        out["output_config"] = oc
    return out


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
