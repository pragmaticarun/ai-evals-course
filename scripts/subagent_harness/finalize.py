"""Write fixtures/recorded/*.jsonl from the harness's subagent answers.

    python scripts/subagent_harness/finalize.py <harness_dir>

Run it after a collect pass that queued nothing. Every (namespace, key) the consumers read
(<dir>/used.jsonl) becomes one record tagged "source": "subagent-authored". A subagent has no
token counter or wall clock, so usage and latency use module 11's documented formula
(scripts/author_module11_fixtures.py): tokens are characters / 4, and latency is
base + per-token costs times lognormal jitter, with a 3% slow tail. With prompt caching, the
first request (lowest key) for each cached prefix writes it, and the others read it.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "labs" / "evalkit" / "src"))

from evalkit.fixtures import canonical_json  # noqa: E402

LATENCY = {"sonnet": (600, 0.12, 0.012, 22), "haiku": (250, 0.04, 0.004, 8)}
SIGMA, TAIL_P, TAIL_X = 0.25, 0.03, 4.0
RECORDED_AT = "2026-11-23T12:00:00+05:30"
SRC = "subagent-authored"
CHAINS = {  # labs/mediadoctor/src/mediadoctor/lab08.py and lab09.py
    "mediadoctor-m8-agent": ("mediadoctor-m5", "mediadoctor-m6"),
    "mediadoctor-m8-judges": ("mediadoctor-judges",),
    "mediadoctor-m9-judges": ("mediadoctor-judges",),
}


def u(*parts: object) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:15], 16) / 16**15


def latency_ms(fam: str, uncached: int, cached: int, out: int, key: str) -> float:
    base, per_in, per_cached, per_out = LATENCY[fam]
    ms = base + per_in * uncached + per_cached * cached + per_out * out
    z = NormalDist().inv_cdf(min(max(u(key, "jitter"), 1e-6), 1 - 1e-6))
    ms *= math.exp(SIGMA * z - SIGMA**2 / 2)
    if u(key, "tail") < TAIL_P:
        ms *= TAIL_X
    return round(ms, 1)


def cached_prefix(req: dict) -> str | None:
    if "cache_control" not in canonical_json({"s": req.get("system"), "t": req.get("tools")}):
        return None
    return canonical_json({"model": req["model"], "s": req.get("system"), "t": req.get("tools")})


def main(hdir: Path) -> None:
    answers = {}
    for line in (hdir / "answers.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            a = json.loads(line)
            answers[a["key"]] = a
    used: dict[str, dict[str, int]] = defaultdict(dict)
    for line in (hdir / "used.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        used[r["ns"]][r["key"]] = r["trial"]
    # Replay chains read the first namespace that has the key. The harness says every store has
    # every key, so a chain logs its reads under its first namespace. Keep a key there only when
    # no later namespace of the chain reads it directly (that is how the course's files are split).
    for first, later in CHAINS.items():
        for key in list(used.get(first, {})):
            if any(key in used.get(ns, {}) for ns in later):
                del used[first][key]
        if first == "mediadoctor-m8-agent" and used.get(first):
            raise SystemExit(f"{len(used[first])} lab08 agent keys are read nowhere else")
        if not used.get(first):
            used.pop(first, None)
    for ns, keys in sorted(used.items()):
        writers: dict[str, str] = {}
        for key in sorted(keys):
            pre = cached_prefix(answers[key]["request"])
            if pre is not None:
                writers.setdefault(pre, key)
        lines = []
        for key in sorted(keys):
            a = answers[key]
            req, resp = a["request"], json.loads(json.dumps(a["response"]))
            fam = "haiku" if "haiku" in req["model"] else "sonnet"
            total = len(canonical_json(req)) // 4
            out = max(1, len(canonical_json(resp["content"])) // 4)
            usage = {"input_tokens": total, "output_tokens": out}
            cached = 0
            pre = cached_prefix(req)
            if pre is not None:
                n = len(pre) // 4
                if writers[pre] == key:
                    usage.update(input_tokens=total - n, cache_creation_input_tokens=n,
                                 cache_read_input_tokens=0)
                else:
                    usage.update(input_tokens=total - n, cache_read_input_tokens=n,
                                 cache_creation_input_tokens=0)
                    cached = n
            resp["usage"] = usage
            rec = {"request_sha256": key, "request": req, "response": resp,
                   "recorded_at": RECORDED_AT, "source": SRC,
                   "latency_ms": latency_ms(fam, total - cached, cached, out, key)}
            if keys[key]:
                rec["trial"] = keys[key]
            lines.append(canonical_json(rec))
        path = ROOT / "fixtures" / "recorded" / f"{ns}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{ns}: {len(lines)} records")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
