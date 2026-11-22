"""LLM-as-judge evaluators and how to trust them (module 5).

A judge here is one binary classifier for one failure mode:

    JudgeSpec (a TOML file)  ->  build_judge_request(spec, item)  ->  the `judge` model
                             ->  {"critique": "...", "verdict": "PASS" | "FAIL"}

and it is validated like any classifier, against human labels:

    confusion(human, judge)  ->  TPR (judge passes what humans pass), TNR (judge fails what humans fail)
    corrected_pass_rate      ->  the Rogan-Gladen correction of a judge-measured pass rate
    bootstrap_corrected      ->  a percentile bootstrap interval for that corrected rate

Convention: PASS is the positive class, as in the course text. A judge that misses failures has a low
TNR; a judge that fails good answers has a low TPR.
"""

from __future__ import annotations

import json
import random
import re
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalkit.config import load_models

VERDICTS = ("PASS", "FAIL")


# --- Judge specs ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Example:
    case_id: str
    verdict: str
    critique: str


@dataclass(frozen=True)
class JudgeSpec:
    name: str
    version: str
    mode: str  # the failure mode this judge detects (a FAIL verdict means the mode is present)
    criterion: str
    pass_def: str
    fail_def: str
    context: tuple[str, ...]  # which parts of a trace the judge sees: question, tools, answer
    examples: tuple[Example, ...] = ()
    notes: str = ""
    path: str = field(default="", compare=False)

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"


def load_judge(path: Path | str) -> JudgeSpec:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    examples = tuple(
        Example(str(e["case_id"]), str(e["verdict"]).upper(), " ".join(str(e["critique"]).split()))
        for e in raw.get("example", [])
    )
    for e in examples:
        if e.verdict not in VERDICTS:
            raise ValueError(f"{path}: example {e.case_id} has verdict {e.verdict!r}")
    context = tuple(raw.get("context", ["question", "tools", "answer"]))
    unknown = set(context) - {"question", "tools", "answer"}
    if unknown:
        raise ValueError(f"{path}: unknown context parts {sorted(unknown)}")
    return JudgeSpec(
        name=raw["name"],
        version=raw["version"],
        mode=raw["mode"],
        criterion=raw["criterion"].strip(),
        pass_def=raw["pass"].strip(),
        fail_def=raw["fail"].strip(),
        context=context,
        examples=examples,
        notes=raw.get("notes", "").strip(),
        path=str(path),
    )


# --- Prompts ------------------------------------------------------------------------------------------

JUDGE_SYSTEM = """\
You evaluate one aspect of answers from MediaDoctor, an assistant for Android and multimedia
engineers. You check exactly one criterion; ignore every other quality of the answer.

Criterion: {criterion}

PASS: {pass_def}

FAIL: {fail_def}

{examples}Read the material, write a short critique that quotes the specific words your verdict rests on,
then give the verdict. Respond with JSON only:
{{"critique": "<two or three sentences>", "verdict": "PASS" or "FAIL"}}"""


@dataclass(frozen=True)
class Item:
    """What a judge may see of one trace. Rendered according to the spec's `context`."""

    case_id: str
    question: str
    answer: str
    tools: tuple[tuple[str, str, str, bool], ...] = ()  # (tool, arguments, result, ok)


def render_item(item: Item, context: Iterable[str], max_result_chars: int = 2500) -> str:
    parts = []
    context = tuple(context)
    if "question" in context:
        parts.append(f"<question>\n{item.question}\n</question>")
    if "tools" in context:
        if item.tools:
            lines = []
            for name, args, result, ok in item.tools:
                status = "" if ok else " (ERROR)"
                res = (
                    result
                    if len(result) <= max_result_chars
                    else result[:max_result_chars] + " ..."
                )
                lines.append(f"- {name} {args}{status}\n  result: {res}")
            parts.append("<tool_calls>\n" + "\n".join(lines) + "\n</tool_calls>")
        else:
            parts.append("<tool_calls>\n(none)\n</tool_calls>")
    if "answer" in context:
        parts.append(f"<answer>\n{item.answer}\n</answer>")
    return "\n".join(parts)


def render_examples(spec: JudgeSpec, items: Mapping[str, Item]) -> str:
    if not spec.examples:
        return ""
    blocks = []
    for i, e in enumerate(spec.examples, 1):
        body = render_item(items[e.case_id], spec.context)
        verdict = json.dumps({"critique": e.critique, "verdict": e.verdict})
        blocks.append(f"Example {i}:\n{body}\nOutput: {verdict}")
    return "Examples:\n\n" + "\n\n".join(blocks) + "\n\n"


def build_judge_request(
    spec: JudgeSpec, item: Item, example_items: Mapping[str, Item]
) -> dict[str, Any]:
    """One judge call. The model and max_tokens come from the `judge` role in config/models.toml."""
    role = load_models()["judge"]
    system = JUDGE_SYSTEM.format(
        criterion=spec.criterion,
        pass_def=spec.pass_def,
        fail_def=spec.fail_def,
        examples=render_examples(spec, example_items),
    )
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": render_item(item, spec.context)}],
    }


_JSON = re.compile(r"\{.*\}", re.S)


@dataclass(frozen=True)
class Verdict:
    case_id: str
    passed: bool | None  # None: unparseable output (count it, never guess)
    critique: str


def parse_verdict(case_id: str, text: str) -> Verdict:
    """Parse the judge's JSON, tolerating code fences or text around it."""
    m = _JSON.search(text)
    if m:
        try:
            obj = json.loads(m.group(0))
            v = str(obj.get("verdict", "")).strip().upper()
            if v in VERDICTS:
                return Verdict(case_id, v == "PASS", str(obj.get("critique", "")))
        except json.JSONDecodeError:
            pass
    return Verdict(case_id, None, text.strip())


# --- Leakage -----------------------------------------------------------------------------------------


def leakage_problems(
    spec: JudgeSpec,
    splits: Mapping[str, str],
    forbidden_text: Iterable[str] = (),
) -> list[str]:
    """Ways a judge prompt can leak evaluation data into the judge.

    - a few-shot example taken from the dev or test split (or with no known split);
    - reference material that should not be in the prompt, such as the expected answer or the
      human label's note, given as `forbidden_text`.
    """
    problems = []
    for e in spec.examples:
        split = splits.get(e.case_id)
        if split != "train":
            problems.append(f"example {e.case_id} comes from split {split!r}, not train")
    prompt = " ".join(
        [spec.criterion, spec.pass_def, spec.fail_def, *(e.critique for e in spec.examples)]
    )
    for text in forbidden_text:
        if text and text.lower() in prompt.lower():
            problems.append(f"prompt contains reference text: {text[:60]!r}")
    return problems


# --- Validation --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Confusion:
    """PASS is positive. tp: both pass; tn: both fail; fp: judge passes a human fail; fn: judge
    fails a human pass."""

    tp: int
    fn: int
    tn: int
    fp: int
    unparsed: int = 0

    @property
    def n(self) -> int:
        return self.tp + self.fn + self.tn + self.fp

    @property
    def tpr(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else float("nan")

    @property
    def tnr(self) -> float:
        return self.tn / (self.tn + self.fp) if self.tn + self.fp else float("nan")

    @property
    def agreement(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else float("nan")

    def __str__(self) -> str:
        return (
            f"n={self.n} (human pass {self.tp + self.fn}, fail {self.tn + self.fp})  "
            f"TPR {self.tpr:.2f} ({self.tp}/{self.tp + self.fn})  "
            f"TNR {self.tnr:.2f} ({self.tn}/{self.tn + self.fp})  agreement {self.agreement:.2f}"
            + (f"  unparsed {self.unparsed}" if self.unparsed else "")
        )


def confusion(human: Mapping[str, bool], judged: Mapping[str, bool | None]) -> Confusion:
    """Compare on the ids both have. An unparsed judge output counts as a FAIL verdict and is
    reported separately: a judge that cannot answer has not passed anything."""
    tp = fn = tn = fp = unparsed = 0
    for cid in sorted(set(human) & set(judged)):
        h, j = human[cid], judged[cid]
        if j is None:
            unparsed += 1
            j = False
        if h and j:
            tp += 1
        elif h:
            fn += 1
        elif j:
            fp += 1
        else:
            tn += 1
    return Confusion(tp, fn, tn, fp, unparsed)


def disagreements(
    human: Mapping[str, bool], judged: Mapping[str, bool | None]
) -> list[tuple[str, str]]:
    out = []
    for cid in sorted(set(human) & set(judged)):
        if bool(judged[cid]) != human[cid]:
            out.append((cid, "judge FAIL, human PASS" if human[cid] else "judge PASS, human FAIL"))
    return out


def corrected_pass_rate(p_observed: float, tpr: float, tnr: float) -> float:
    """Rogan-Gladen: the true pass rate implied by a judge's observed pass rate.

    observed = true * TPR + (1 - true) * (1 - TNR)   =>   true = (observed + TNR - 1) / (TPR + TNR - 1)

    Clipped to [0, 1]. Undefined when TPR + TNR <= 1 (the judge is no better than chance).
    """
    denom = tpr + tnr - 1
    if denom <= 0:
        raise ValueError(f"TPR + TNR must exceed 1 (got {tpr:.2f} + {tnr:.2f})")
    return min(1.0, max(0.0, (p_observed + tnr - 1) / denom))


@dataclass(frozen=True)
class Estimate:
    observed: float
    corrected: float
    low: float
    high: float
    n_unlabelled: int
    n_labelled: int
    draws: int

    def __str__(self) -> str:
        return (
            f"observed pass rate {self.observed:.3f} on {self.n_unlabelled} unlabelled traces; "
            f"corrected {self.corrected:.3f}, 95% CI [{self.low:.3f}, {self.high:.3f}] "
            f"({self.draws} bootstrap draws, judge error from {self.n_labelled} labelled traces)"
        )


def bootstrap_corrected(
    labelled: list[tuple[bool, bool]],
    unlabelled: list[bool],
    draws: int = 2000,
    seed: int = 0,
    level: float = 0.95,
) -> Estimate:
    """Corrected pass rate with a percentile bootstrap interval.

    `labelled` is (human_pass, judge_pass) on a held-out labelled set (the test split): it estimates
    the judge's TPR and TNR. `unlabelled` is the judge's verdicts on the traffic you want to measure.
    Both are resampled with replacement in every draw, so the interval includes uncertainty about the
    judge as well as about the traffic. Draws where TPR + TNR <= 1 are skipped and counted.
    """

    def tpr_tnr(pairs: list[tuple[bool, bool]]) -> tuple[float, float]:
        pos = [j for h, j in pairs if h]
        neg = [j for h, j in pairs if not h]
        if not pos or not neg:
            return float("nan"), float("nan")
        return sum(pos) / len(pos), sum(not j for j in neg) / len(neg)

    p_obs = sum(unlabelled) / len(unlabelled)
    tpr, tnr = tpr_tnr(labelled)
    point = corrected_pass_rate(p_obs, tpr, tnr)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        lab = [labelled[rng.randrange(len(labelled))] for _ in labelled]
        unl = [unlabelled[rng.randrange(len(unlabelled))] for _ in unlabelled]
        t1, t0 = tpr_tnr(lab)
        if not (t1 + t0 > 1):  # nan or a useless judge in this resample
            continue
        samples.append(corrected_pass_rate(sum(unl) / len(unl), t1, t0))
    samples.sort()
    alpha = (1 - level) / 2
    lo = samples[int(alpha * (len(samples) - 1))]
    hi = samples[int((1 - alpha) * (len(samples) - 1))]
    return Estimate(p_obs, point, lo, hi, len(unlabelled), len(labelled), len(samples))


def run_judge(
    create: Callable[..., dict[str, Any]],
    spec: JudgeSpec,
    items: Iterable[Item],
    example_items: Mapping[str, Item],
    text_of: Callable[[dict[str, Any]], str],
) -> dict[str, Verdict]:
    """Run one judge over items; `create` is LLM.create (replay, record, or live)."""
    out = {}
    for item in items:
        resp = create(**build_judge_request(spec, item, example_items))
        out[item.case_id] = parse_verdict(item.case_id, text_of(resp))
    return out
