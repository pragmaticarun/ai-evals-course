# Cheat sheet: evaluating architectures

Score each component on its own labels, keep the end-to-end outcome as the headline, and use the component numbers
to choose the next fix. Module 7; code in `evalkit.retrieval`, `evalkit.trajectory`, and `mediadoctor.lab07`.

## RAG: retrieval

Labels: queries paired with the passages (sections) that answer them; grade 2 = answers, 1 = related.

| Metric | One query | Use when |
|---|---|---|
| recall@k | relevant in top k / all relevant | the generator reads the top k |
| hit@k | 1 if any answering passage is in the top k | one passage is enough to answer |
| precision@k | relevant in top k / k | irrelevant context distracts or costs tokens |
| MRR | mean of 1 / rank of the first relevant | people scan a ranked list |
| nDCG@k | DCG / ideal DCG, gain = grade, discount log2(rank + 1) | graded relevance; order matters |

- Average over queries; bootstrap the mean over queries; compare configs paired on the same queries.
- Read per-topic numbers with their n. Write hard negatives (same words, different answer) into the set.
- Label sections, not chunks, so different chunkers are scored against the same labels.

## RAG: generation

| Check | Compares | Evaluator | Fails when |
|---|---|---|---|
| faithfulness / groundedness | answer vs context | validated judge | a fact is not in the passages (even a true one) |
| answer relevance | answer vs question | validated judge | off-topic, or only declines |
| citation validity | cited ids vs context | code | an id was not retrieved |
| citation support | cited ids vs labels | code | no cited passage is relevant |

## RAG: attribution

| | answer passed | answer failed |
|---|---|---|
| answering passage retrieved | pass | **generation failure** |
| not retrieved | lucky pass | **retrieval failure** |

Ceilings: pass rate if retrieval were perfect ≈ pass rate on hits; if generation were perfect ≈ hit rate.
Fix whichever ceiling is higher.

## Multi-turn

| Level | Checks |
|---|---|
| session (first) | goal reached (resolved); gave up while the user could still help; turns to resolution |
| turn | re-asks a fact already given (retention); asks when nothing was missing (needless); one question per turn; format |
| simulator | volunteers facts not asked for; contradicts or invents facts; check before trusting sessions |

Simulated user = persona + opening + known facts + "reveal only when asked". Alternative: N−1 testing on real
conversation prefixes. Reduce a multi-turn failure to a single-turn test when you can.

## Multi-step and multi-agent

| Layer | Metric |
|---|---|
| outcome | pass/fail on the final state (always first) |
| tools | tool recall and precision vs expected; argument errors |
| order | expected steps are a subsequence of actual steps |
| efficiency | minimal steps / steps taken (≤ 1.0) |
| handoffs | right route; the brief carries every file, device, and log name |

**Transition-failure matrix:** for each failed run, (last state that succeeded, first state that failed). Rows =
last success, columns = first failure. Fix the hottest upstream cell first; count only the first failure.

```python
from evalkit.trajectory import first_failure, format_matrix, transition_matrix

f = first_failure(states, lambda i, s: oks[i])  # ("handoff", "codec_caps") or None
print(format_matrix(*transition_matrix(failures)))
```

## Beyond keyword retrieval, and acting agents

- Dense, hybrid (rank fusion), reranked (measure recall@k before the reranker, nDCG after), contextual chunks:
  each is one more configuration on the same relevance set, with its cost and latency.
- Model-drafted relevance labels: a person accepts or corrects; validate the drafter's TPR/TNR first.
- Agents that act: sandbox with a known start state; assert on the final state in code; pass^k on actions;
  checkpoints for long runs.
- Simulated users: compare with real sessions on the same scenarios before trusting them; until then, an upper bound.

## Multimodal

- Images as `image` content blocks next to the text; a vision judge per artifact (binary), or an answer about the
  image scored by a code check.
- Make labelled images: a generation recipe is a label (e.g. FFmpeg quantiser for blocking, bit depth for banding).
- Report per artifact and per severity with Wilson intervals; ±0.15 needs 30 to 45 images per cell.
- Review disagreements: recipe labels can be incomplete (a blocked gradient also bands).
- Fixtures: hash base64 payloads (`evalkit.fixtures.compact_request`) instead of storing them.
