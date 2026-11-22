"""Golden datasets (module 8): versioned, hashed, and with a held-out split that stays held out.

A golden dataset is the fixed set of cases, labels, and evaluator configs that a gate measures against.
Its manifest records a version and the SHA-256 of every file it is made of, plus a digest of each
split's case ids. `check_manifest` lists what changed, so CI fails when someone edits a label, a
judge spec, or a recorded fixture without bumping the version (and re-reading the numbers).

The held-out split is for release decisions only. `HoldoutGuard` refuses to hand its ids to anything
that is not marked as a release evaluation and keeps a log of every look; `rotate` swaps fresh cases
in once the held-out set has been looked at too often.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "evalkit-golden/1"


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ids_digest(ids: Iterable[str]) -> str:
    """Order-free digest of a set of case ids."""
    return hashlib.sha256("\n".join(sorted(set(ids))).encode()).hexdigest()


def build_manifest(
    name: str,
    version: str,
    root: Path,
    files: Sequence[str],
    splits: Mapping[str, Sequence[str]],
    **meta: Any,
) -> dict[str, Any]:
    """A manifest for `files` (paths relative to `root`) and the case ids of each split."""
    return {
        "schema": MANIFEST_SCHEMA,
        "name": name,
        "version": version,
        **meta,
        "files": {
            f: {"sha256": sha256_file(root / f), "bytes": (root / f).stat().st_size}
            for f in sorted(files)
        },
        "splits": {s: {"n": len(ids), "ids_sha256": ids_digest(ids)} for s, ids in splits.items()},
    }


def check_manifest(
    manifest: Mapping[str, Any],
    root: Path,
    splits: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """Differences between the manifest and the files (and splits) as they are now."""
    problems = []
    for f, info in manifest.get("files", {}).items():
        path = root / f
        if not path.is_file():
            problems.append(f"{f}: missing")
        elif sha256_file(path) != info["sha256"]:
            problems.append(f"{f}: changed since version {manifest.get('version')}")
    for s, ids in (splits or {}).items():
        info = manifest.get("splits", {}).get(s)
        if info is None:
            problems.append(f"split {s!r}: not in the manifest")
        elif ids_digest(ids) != info["ids_sha256"] or len(set(ids)) != info["n"]:
            problems.append(
                f"split {s!r}: case ids changed ({len(set(ids))} now, {info['n']} listed)"
            )
    return problems


def load_manifest(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_manifest(path: Path | str, manifest: Mapping[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def bump(version: str, part: str = "minor") -> str:
    """Semantic version bump: major for new cases or splits, minor for relabels, patch for fixes."""
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


# --- The held-out split --------------------------------------------------------------------------------


class HoldoutAccessError(PermissionError):
    pass


@dataclass
class HoldoutGuard:
    """Hands out held-out ids only for release evaluations, and logs every look."""

    holdout: frozenset[str]
    log: list[tuple[str, int]] = field(default_factory=list)  # (purpose, n cases)

    def check(self, ids: Iterable[str], purpose: str, release: bool = False) -> list[str]:
        ids = list(ids)
        touched = [i for i in ids if i in self.holdout]
        if touched and not release:
            raise HoldoutAccessError(
                f"{purpose!r} asked for {len(touched)} held-out case(s), e.g. {touched[0]}; "
                "only a release evaluation may read the held-out split"
            )
        if touched:
            self.log.append((purpose, len(touched)))
        return ids

    @property
    def looks(self) -> int:
        return len(self.log)


def rotate(
    gate: Sequence[str],
    holdout: Sequence[str],
    fresh: Sequence[str],
    n: int,
    seed: int = 0,
) -> tuple[list[str], list[str]]:
    """Move `n` fresh cases into the held-out split and `n` held-out cases into the gate set.

    The held-out cases that leave are no longer held out (people have seen their results), so they
    join the gate set; the fresh cases have never been used for any decision.
    """
    if n > len(fresh) or n > len(holdout):
        raise ValueError(f"cannot rotate {n} cases: {len(fresh)} fresh, {len(holdout)} held out")
    rng = random.Random(seed)
    leaving = set(rng.sample(sorted(holdout), n))
    new_holdout = sorted([h for h in holdout if h not in leaving] + list(fresh[:n]))
    new_gate = sorted(list(gate) + sorted(leaving))
    return new_gate, new_holdout
