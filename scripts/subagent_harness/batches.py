"""Turn the harness's pending requests into task files for subagents, and merge their answers.

    python scripts/subagent_harness/batches.py prepare <harness_dir> <round>
    python scripts/subagent_harness/batches.py merge   <harness_dir> <round>

prepare: dedupes <dir>/pending.jsonl by key, renders each request as readable text in
<dir>/rounds/<round>/tasks/<key>.md, and groups them into batches (one subagent each) in
<dir>/rounds/<round>/batches.json. Batches never mix models, and never hold two trials of the
same request, so repeated runs (module 6) are answered independently.

merge: validates every <dir>/rounds/<round>/answers/<key>.json and appends it to
<dir>/answers.jsonl. Prints the keys that are missing or invalid.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATCH_CHARS = {"sonnet": 150_000, "haiku": 150_000}
BATCH_MAX = {"sonnet": 30, "haiku": 40}


def family(model: str) -> str:
    return "haiku" if "haiku" in model else "sonnet"


def image_index() -> dict[str, Path]:
    """sha256 of the base64 text of each repo image -> its path (requests store only the hash)."""
    out = {}
    for p in [
        *ROOT.glob("data/**/*.png"),
        *ROOT.glob("data/**/*.jpg"),
        *ROOT.glob("docs/**/*.png"),
    ]:
        b64 = base64.standard_b64encode(p.read_bytes())
        out[hashlib.sha256(b64).hexdigest()] = p
    return out


def _system_text(system) -> str:
    if system is None:
        return "(none)"
    if isinstance(system, str):
        return system
    return "\n\n".join(b.get("text", "") for b in system)


def _block(b: dict, images: dict[str, Path]) -> str:
    t = b.get("type")
    if t == "text":
        return b["text"]
    if t == "image":
        src = b["source"]
        p = images.get(src.get("data_sha256", ""))
        where = str(p) if p else f"(image not found, sha256 {src.get('data_sha256')})"
        return f"[IMAGE: open and look at this file with your Read tool: {where}]"
    if t == "tool_use":
        return "TOOL CALL " + json.dumps(
            {"id": b["id"], "name": b["name"], "input": b.get("input", {})}
        )
    if t == "tool_result":
        c = b.get("content")
        if isinstance(c, list):
            c = "\n".join(x.get("text", "") for x in c)
        err = " (is_error)" if b.get("is_error") else ""
        try:  # pretty-print JSON so no line is long (the Read tool cuts lines over 2000 chars)
            c = json.dumps(json.loads(c), indent=1, ensure_ascii=False)
        except TypeError, ValueError:
            pass
        return f"TOOL RESULT for {b['tool_use_id']}{err}:\n{c}"
    return json.dumps(b)


def render(req: dict, images: dict[str, Path]) -> str:
    parts = ["# Request", f"model: {req['model']}   max_tokens: {req.get('max_tokens')}", ""]
    parts += ["## System prompt", _system_text(req.get("system")), ""]
    if req.get("tools"):
        parts += ["## Tools you may call (JSON schemas)"]
        for t in req["tools"]:
            parts.append(json.dumps({k: t[k] for k in ("name", "description", "input_schema")}))
        parts.append("")
    parts.append("## Conversation so far")
    for m in req["messages"]:
        c = m["content"]
        body = c if isinstance(c, str) else "\n\n".join(_block(b, images) for b in c)
        parts += [f"### {m['role'].upper()}", body, ""]
    parts.append("## Your job: write the next ASSISTANT turn.")
    return wrap_long("\n".join(parts))


def wrap_long(text: str, width: int = 1200) -> str:
    """Hard-wrap lines longer than `width` (marked with a trailing backslash)."""
    out = []
    for line in text.split("\n"):
        while len(line) > width:
            out.append(line[:width] + "\\")
            line = line[width:]
        out.append(line)
    return "\n".join(out)


def prepare(hdir: Path, rnd: str) -> None:
    pending: dict[str, dict] = {}
    for line in (hdir / "pending.jsonl").read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        pending.setdefault(p["key"], p)
    done = set()
    if (hdir / "answers.jsonl").exists():
        done = {
            json.loads(x)["key"] for x in (hdir / "answers.jsonl").read_text().splitlines() if x
        }
    pending = {k: v for k, v in pending.items() if k not in done}
    rdir = hdir / "rounds" / rnd
    (rdir / "tasks").mkdir(parents=True, exist_ok=True)
    (rdir / "answers").mkdir(parents=True, exist_ok=True)
    images = image_index()
    groups: dict[tuple, list] = defaultdict(list)
    for key, p in sorted(pending.items(), key=lambda kv: (kv[1]["ns"], kv[1]["trial"], kv[0])):
        text = render(p["request"], images)
        (rdir / "tasks" / f"{key}.md").write_text(text, encoding="utf-8")
        (rdir / "tasks" / f"{key}.request.json").write_text(json.dumps(p), encoding="utf-8")
        groups[(family(p["request"]["model"]), p["ns"], p["trial"])].append((key, len(text)))
    batches = []
    for (fam, ns, trial), items in groups.items():
        cur, size = [], 0
        for key, n in items:
            if cur and (size + n > BATCH_CHARS[fam] or len(cur) >= BATCH_MAX[fam]):
                batches.append({"model": fam, "ns": ns, "trial": trial, "keys": cur})
                cur, size = [], 0
            cur.append(key)
            size += n
        if cur:
            batches.append({"model": fam, "ns": ns, "trial": trial, "keys": cur})
    for i, b in enumerate(batches):
        b["id"] = f"{rnd}-{i:03d}"
        (rdir / f"batch-{b['id']}.txt").write_text("\n".join(b["keys"]) + "\n", encoding="utf-8")
    (rdir / "batches.json").write_text(json.dumps(batches, indent=1), encoding="utf-8")
    by = defaultdict(int)
    for b in batches:
        by[b["model"]] += 1
    print(f"{len(pending)} requests -> {len(batches)} batches {dict(by)}")


def validate(ans: dict, req: dict) -> str | None:
    content = ans.get("content")
    if not isinstance(content, list) or not content:
        return "content must be a non-empty list"
    tools = {t["name"]: t for t in req.get("tools") or []}
    for b in content:
        if b.get("type") == "text":
            if not isinstance(b.get("text"), str) or not b["text"].strip():
                return "empty text block"
        elif b.get("type") == "tool_use":
            if b.get("name") not in tools:
                return f"unknown tool {b.get('name')!r}"
            if not isinstance(b.get("input"), dict):
                return "tool_use input must be an object"
            missing = set(tools[b["name"]]["input_schema"].get("required", [])) - set(b["input"])
            if missing:
                return f"{b['name']} missing required {sorted(missing)}"
            # A named file or device must come from the conversation (catches answers written
            # to the wrong key).
            seen = json.dumps(req["messages"]).lower()
            for arg in ("file", "device", "log", "path"):
                v = b["input"].get(arg)
                if isinstance(v, str) and v and v.lower().split("/")[-1] not in seen:
                    # A model may infer or guess a name, so this is only reported.
                    print(f"   note: {b['name']} {arg}={v!r} is not in the conversation")
        else:
            return f"unsupported block type {b.get('type')!r}"
    if "PENDING-ANSWER" in json.dumps(content):
        return "placeholder text in answer"
    return None


def merge(hdir: Path, rnd: str) -> None:
    rdir = hdir / "rounds" / rnd
    batches = json.loads((rdir / "batches.json").read_text())
    ok, bad = 0, []
    with (hdir / "answers.jsonl").open("a", encoding="utf-8") as out:
        for b in batches:
            for key in b["keys"]:
                p = json.loads((rdir / "tasks" / f"{key}.request.json").read_text())
                f = rdir / "answers" / f"{key}.json"
                if not f.exists():
                    bad.append((b["id"], key, "missing"))
                    continue
                try:
                    ans = json.loads(f.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    bad.append((b["id"], key, f"invalid JSON: {exc}"))
                    continue
                if isinstance(ans, list):
                    ans = {"content": ans}
                err = validate(ans, p["request"])
                if err:
                    bad.append((b["id"], key, err))
                    continue
                content, n = [], 0
                for blk in ans["content"]:
                    if blk["type"] == "tool_use":
                        tid = "toolu_sa_" + hashlib.sha256(f"{key}:{n}".encode()).hexdigest()[:20]
                        content.append(
                            {
                                "type": "tool_use",
                                "id": tid,
                                "name": blk["name"],
                                "input": blk["input"],
                            }
                        )
                        n += 1
                    else:
                        content.append({"type": "text", "text": blk["text"].strip()})
                stop = "tool_use" if n else "end_turn"
                resp = {
                    "id": f"msg_subagent_{key[:16]}",
                    "type": "message",
                    "role": "assistant",
                    "model": p["request"]["model"],
                    "content": content,
                    "stop_reason": stop,
                    "usage": {
                        "input_tokens": len(json.dumps(p["request"])) // 4,
                        "output_tokens": max(1, len(json.dumps(content)) // 4),
                    },
                }
                out.write(
                    json.dumps(
                        {
                            "key": key,
                            "ns": p["ns"],
                            "trial": p["trial"],
                            "request": p["request"],
                            "response": resp,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                ok += 1
    print(f"merged {ok}; problems {len(bad)}")
    for row in bad:
        print("  ", *row)


if __name__ == "__main__":
    cmd, hdir, rnd = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    {"prepare": prepare, "merge": merge}[cmd](hdir, rnd)
