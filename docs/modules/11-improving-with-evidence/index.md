# 11. Improving with evidence: accuracy, latency, cost

**Goal:** run experiments that move MediaDoctor's metrics, prove which change moved them, and turn the result into
a decision someone else can trust.

**Estimated time:** 8 hours (lesson 2.5 h, lab 3.5 h, exercises and quiz 2 h)

By the end of this module you will be able to:

- choose what to fix first from a failure taxonomy, by the expected value of fixing each mode;
- design an experiment that changes one thing, with a metric and a decision rule written down before the run, a
  dev set to iterate on, and a held-out set you look at once;
- measure the three axes together: task success with a confidence interval, p50 and p95 latency with timeouts, and
  cost per task and **cost per successful task**;
- improve a prompt from error analysis, choose few-shot examples without leaking the eval set, and explain what
  automated prompt optimizers such as DSPy do;
- compare models (Sonnet against Haiku), routing and cascades, retries with a self-check, and prompt caching, each
  with its cost and latency;
- draw an accuracy against cost Pareto frontier and pick a point on it with uncertainty in view;
- know when to stop optimizing;
- report the result: an experiment log, a one-page decision memo, honest uncertainty, and the claims to avoid.

Artifacts: the **experiment log** (`uv run mediadoctor-lab11 log`), the **accuracy vs cost frontier**
(`uv run mediadoctor-lab11 pareto --svg runs/m11/pareto.svg`), a **decision memo**
(`uv run mediadoctor-lab11 memo`), the pre-registration (`config/experiments/preregistration.toml`), and the
[cost and latency cheat sheet](../../cheatsheets/cost-latency.md). Templates: the
[experiment log](../../eval-templates/experiment-log.md), the [decision memo](../../eval-templates/decision-memo.md),
and module 12's [eval report](../../eval-templates/eval-report.md).

## Intuition: pay for answers, not for calls

A cheap call that gives a wrong answer is not cheap. Someone acts on it, it fails, they come back, and either a
person fixes it or the agent runs again. The number that matters is what you spend to get **one task done right**:

```text
cost per successful task = (total cost of every call for every task) / (number of tasks that succeeded)
```

Media engineers already think this way about encoders. A faster preset that needs a second pass to hit the bitrate
target is not faster; the unit you care about is "seconds per file that meets spec", not "seconds per pass". In
this module a Haiku-only MediaDoctor costs about a twentieth of the Sonnet version per task, and it still loses,
because it gets 21 points fewer tasks right, and those tasks are what the user came for. Meanwhile one change that does
not touch the model or the answers at all, prompt caching, cuts the bill by more than half.

The other half of the intuition: **with LLMs, every change changes everything a little**. A longer prompt is more
accurate and slower and more expensive. A retry fixes some answers and doubles the time of the tasks it touches. So
change one thing at a time, measure all three axes every time, and decide by a rule you wrote down before you saw
the numbers.

## Step 1: choose what to fix, by expected value

Module 3 gave you a failure taxonomy with counts, severity, and a guess at how easy each mode is to fix. Turn that
into a ranking. For each mode:

```text
value   = rate x severity x P(the fix works)        # severity-weighted failures removed, per task
per day = value / effort in days
```

`uv run mediadoctor-lab11 ev` does this on module 3's 100 labelled traces, with P(fix) of 0.8, 0.6, and 0.3 for
easy, medium, and hard modes and an effort of 1, 3, and 8 days:

```text
  mode                      rate        95% CI sev    fix  value per day
  ignored-tool-output       0.11 [0.06, 0.19]   3 medium   19.8     6.6
  fabricated-evidence       0.08 [0.04, 0.15]   3   easy   19.2    19.2
  wrong-tool-args           0.08 [0.04, 0.15]   2   easy   12.8    12.8
  skipped-investigation     0.08 [0.04, 0.15]   2   easy   12.8    12.8
  wrong-api-detail          0.08 [0.04, 0.15]   2 medium    9.6     3.2
  ...
  format-violation          0.02 [0.01, 0.07]   1   easy    1.6     1.6
```

Three things to take from it. First, the two highest-value modes (the answer contradicting the tool output, and
citing evidence that was never obtained) are both severe; that is where the v3 prompt in this module aims. Second,
format violations, the easiest thing to fix and the most visible in a demo, are worth almost nothing. Third, look at
the intervals: with 100 traces you can rank the big modes against the small ones, but not the top four against each
other. Do not argue for a week about whether mode 1 or mode 2 comes first; take the cheap one, ship it, and re-run
error analysis.

The P(fix) and effort numbers are guesses, and that is fine. Writing them down turns "I think we should fix X" into
an estimate a colleague can disagree with specifically. Hamel Husain and Shreya Shankar make the related point that
[not every failure mode deserves an automated evaluator](https://hamel.dev/blog/posts/evals-faq/should-i-build-automated-evaluators-for-every-failure-mode-i-find.html):
the same cost-benefit thinking applies to fixes.

## Step 2: design the experiment before you run it

An experiment that can be read honestly has five parts, and all five are written down before the first run.

1. **One change.** Each configuration in `config/experiments/variants.toml` names a parent and differs from it in
   one thing: the prompt, the model, caching, or a strategy. If you change the prompt and the model together and
   success rises, you do not know which did it, and the next person to touch either will undo it by accident. When
   two changes must ship together, run the ablation: each one alone, then both.
2. **A primary metric and a decision rule.** Here: task success (all four checks pass and the task finishes within
   15 seconds), with a superiority rule for changes meant to improve quality (the paired 95% CI for the difference
   must be above zero) and a **non-inferiority** rule for changes meant to save money (the CI's lower bound must be
   above minus 5 points, and cost per success must fall). Guardrail metrics sit alongside: p95 latency under
   12 seconds and cost per success under one cent.
3. **A dev set and a held-out set.** Iterate on dev (108 queries here). Keep the test split (29 queries) for one
   look, by the configuration you have chosen, just before release. Every time you look at a set and change
   something because of it, that set becomes a little more like training data. Module 8's `HoldoutGuard` enforces
   the rule: `confirm` refuses to read the held-out split without `--release`, and logs every look.
4. **A paired comparison.** Every configuration runs on the same queries, so compare them query by query. Paired
   tests are far more sensitive than comparing two independent rates, because most queries come out the same both
   ways; only the ones that changed carry information.
5. **A sample size you checked.** Module 6's `mdd_paired` tells you the smallest difference your dev set can
   reliably see. With 108 queries and 10% of them changing outcome, that is about 8 points. If you hope for a
   2-point gain, this experiment cannot show it; either get more data or do not run it.

Writing all of this down first is **pre-registration**, a practice borrowed from science, where it exists because
researchers who choose their analysis after seeing the data find effects that are not there (Gelman and Loken's
"[garden of forking paths](https://sites.stat.columbia.edu/gelman/research/unpublished/p_hacking.pdf)"). The lab's
`config/experiments/preregistration.toml` and `log.toml` are that record. Kohavi, Tang, and Xu's
[Trustworthy Online Controlled Experiments](https://experimentguide.com/) is the standard reference for the wider
discipline.

## Step 3: measure accuracy, latency, and cost together

`uv run mediadoctor-lab11 report` replays seven configurations on the 108 dev queries:

```text
variant   success         95% CI  p50 s  p95 s       95% CI t/o  cost/task cost/success                95% CI cache
v1          0.667 [0.573, 0.748]   5.09  10.06 [ 7.4, 12.2]   1   $0.00586     $0.00880 [$0.00782, $0.01020]    0%
v2          0.759 [0.671, 0.830]   5.24   8.09 [ 7.5,  8.7]   1   $0.00619     $0.00815 [$0.00734, $0.00919]    0%
v3          0.833 [0.752, 0.892]   5.91  11.61 [ 8.4, 14.4]   2   $0.00818     $0.00981 [$0.00892, $0.01077]    0%
v3-cache    0.852 [0.773, 0.907]   5.14   7.76 [ 7.2,  8.7]   0   $0.00342     $0.00402 [$0.00365, $0.00443]   76%
haiku       0.639 [0.545, 0.723]   1.90   3.30 [ 2.7,  4.4]   0   $0.00018     $0.00028 [$0.00025, $0.00034]   76%
cascade     0.694 [0.602, 0.773]   2.07   7.25 [ 4.8,  8.4]   0   $0.00048     $0.00069 [$0.00044, $0.00100]   77%
retry       0.898 [0.827, 0.942]   5.84  10.42 [ 8.3, 11.3]   0   $0.00384     $0.00428 [$0.00381, $0.00483]   64%
```

**Accuracy** is task success with a Wilson interval, as in module 6. Success here means the final answer passes
module 5's three code checks and a reference check of the diagnosis, and the whole task finished within the
timeout.

**Latency** is the wall time of the whole task, read from the root span of the trace: every model call, every tool,
and every self-check. Report the median (p50, the typical user) and the 95th percentile (p95, the slow experience
one user in twenty has). Averages hide the tail, and the tail is what people remember. Note the intervals on p95:
with 108 tasks, the p95 rests on about five of them, so a difference of a second or two between configurations is
often noise. `evalkit.stats.percentile` interpolates between ranks the way NumPy does, so your numbers will match a
notebook.

A **timeout** turns latency into accuracy. A user who gives up after 15 seconds got no answer, so a task that ran
longer counts as a failure, however good the answer. v3 lost two tasks this way.

**Cost** is computed per call from the usage the API returns, with the prices in `config/models.toml`:

```text
cost = (uncached input x input price + output x output price
        + cache writes x cache-write price + cache reads x cache-read price) / 1,000,000
```

Cost per task averages that over tasks; cost per successful task divides the total by the number of successes, and
its interval comes from a bootstrap over tasks (resample the tasks, recompute the ratio). A configuration that is
cheap per call but needs more calls, or fails more often, shows up here.

## Step 4: the levers, and what each one costs

### Prompt changes, guided by error analysis

The first two experiments are prompt changes, each aimed at a mode the taxonomy ranked high. v2 is module 6's
prompt, which tells the agent to check the user's claims before relying on them. v3 adds three sentences aimed at the
top two modes (quote the exact tool value the cause depends on; when tool output contradicts your expectation the
output wins; cite only tools that returned a result) and two worked examples.

```text
  v2        vs v1        +0.093 [+0.037, +0.157]  only parent  1, only v2 11  cost/success -7%
  v3        vs v2        +0.074 [+0.019, +0.139]  only parent  2, only v3 10  cost/success +20%
```

Both clear the superiority bar. Read the discordant counts, not just the difference: v2 fixed 11 queries and broke
1. Then look at the failure modes behind the numbers (`report` prints them from the reference labels): v2 cut
adopted false premises from 17 to 6 but did nothing for answers that contradict the tool output (10, then 11); v3
halved those. That is the point of aiming a change at a mode: you can check that it hit the mode you aimed at,
and not some other one by luck.

v3 also costs 20% more per success, because the examples add about 400 tokens to every call. Hold that thought.

**Few-shot examples** are the strongest prompt lever and the easiest to get wrong. Choose them from your failures (the
cases the model got wrong in error analysis), rewritten as correct answers, so they teach exactly what the model
lacks. v3's examples come from module 3's traces m3t059 (an answer that ignored ffprobe's start time) and m3t065 (a
citation of a log the agent never managed to read). Two rules:

- **Never take examples from the eval set.** An example that is also a test question measures memory, not skill.
  Less obviously, an example that is a near-copy of a test question does the same. Exercise 3 shows how the first
  draft of v3's first example was a near-copy of two training questions and how to catch it automatically.
- **Examples are part of the prompt.** They cost tokens on every call, and they can over-steer: a model shown two
  examples that both cite `[tool:ffprobe]` may start calling ffprobe when it is not needed. Re-run the whole suite,
  not only the cases the examples target.

**Automated prompt optimizers** such as [DSPy](https://dspy.ai/) ([Khattab et al., 2023](https://arxiv.org/abs/2310.03714))
treat the prompt (instructions and few-shot examples) as parameters and search for the version that scores best on
a metric you supply, using a training set of examples. Conceptually it is hill-climbing on your eval. That makes
them only as good as the metric and as safe as your split discipline: an optimizer will find every weakness in a
grader and will overfit a small dev set with enthusiasm. Hamel Husain and Shreya Shankar's advice is to
[write prompts by hand first](https://hamel.dev/blog/posts/evals-faq/should-i-stop-writing-prompts-manually-in-favor-of-automated-tools.html),
because writing forces you to state your requirements and an optimizer cannot discover failure modes it has no
metric for; once trusted evals exist, an optimizer can help with the last stretch. This course does not depend on
one; if you try one, give it the train split only and judge the result on dev and the held-out set like any other
variant.

### Model choice: Sonnet, Haiku, and cascades

Changing the model is the change people reach for first; Hamel and Shreya's FAQ suggests
[doing error analysis before switching models](https://hamel.dev/blog/posts/evals-faq/how-much-time-should-i-spend-on-model-selection.html),
because the failures are often in the prompt, the tools, or the data. When you do test a model, test it as a
non-inferiority question: is it good enough, for much less?

```text
  haiku     vs v3-cache  -0.213 [-0.296, -0.139]  only parent 23, only haiku  0  cost/success -93%
  cascade   vs v3-cache  -0.157 [-0.231, -0.093]  only parent 17, only cascade  0  cost/success -83%
```

Haiku alone is 93% cheaper per success and 21 points worse; the whole interval is far outside the 5-point margin.
It is not close.

A **cascade** runs the cheap model first and escalates to the expensive one only when something says the cheap
answer is bad (the idea behind [FrugalGPT](https://arxiv.org/abs/2305.05176), which chains models of increasing cost
behind a scorer). Its quality depends entirely on that "something". Here the router is module 5's three code checks:
format, citations, investigated. It escalated 12 of 108 tasks, but Haiku's main failures (adopting a false premise,
contradicting the tool output) produce well-formed, properly cited answers that pass every code check. The router
cannot see them, so they reach the user. A cascade is only as good as its router's recall on the failures that
matter; a better router (a validated judge on the premise and the cause) is a new experiment, with its own cost and
latency. Routing by query difficulty instead (easy questions to Haiku) needs a difficulty signal you have tested the
same way.

### Thinking and effort: the lever to try before a cheaper model

Every request in the course sets thinking and effort explicitly, per model, in `config/models.toml`
(`[generation.<model>]`): thinking off (Sonnet 5.5's `between_tools`, Haiku 5.5's `disabled`) and effort medium for
Sonnet, low for Haiku. Leaving them out is not neutral: both models then think by default, the thinking counts
toward `max_tokens` and is billed as output, and a 1024-token agent can end its turn at `stop_reason: "max_tokens"`
with no answer (the agent loops now mark that as an error on the trace, module 2).

That makes effort and thinking a lever in their own right, and for most teams the first one to measure, before a
cascade: the same model at lower effort often matches a stronger setting on routine work, keeps one prompt cache,
and needs no router. Treat it like any other variant: one change (say `v3-cache` with thinking adaptive and effort
high, with `max_tokens` raised to leave room for it), the same pre-registered rule, success with an interval, p95,
and cost per success, because thinking makes answers slower and longer. The course does not ship recordings for it,
since the synthetic fixtures cannot say what thinking would change; it is the first experiment to run with a key
(module 12's [Make it your own](../12-capstone/extensions.md)).

### Retries and self-checks

The `retry` configuration adds a Haiku judge that reviews each answer against the tool output; on FAIL, the agent
gets the critique and one more try in the same conversation. This is a guardrail in the request path, in Hamel and
Shreya's terms, and they list the two questions to ask:
[latency and cost, and the balance of false positives and false negatives](https://hamel.dev/blog/posts/evals-faq/can-my-evaluators-also-be-used-to-automatically-fix-or-correct-outputs-in-production.html).
Measure both:

```text
Retry: the self-check sent 15/108 tasks back (14 of 16 defective answers caught, 1 false alarms on 92 good ones);
6 of the 15 retried tasks ended correct.
retry     vs v3-cache  +0.046 [+0.009, +0.093]  only parent  0, only retry  5  cost/success +6%  p95 +2.67 s
```

The judge is good (TPR 14/16, one false alarm), but catching a defect is not fixing it: only 5 of the 14 caught
defects were fixed on the second try. Every task pays for the judge call (about 0.4 s and a little money); the 15
retried tasks pay for a second agent turn (about 3.5 s each). The gain clears the pre-registered bar, but only just,
and the exact McNemar test on 5 fixed against 0 broken gives p = 0.06. Two reasonable tests disagree at this size,
and module 6 already said which one to believe: with fewer than about 10 discordant tasks the bootstrap interval
comes out too narrow, and the exact test should decide. So the pre-registration named the wrong test for a step this
small. That is a mistake in the registration, and it is worth seeing how to handle one:

- **Do not change the rule now.** Switching to McNemar after seeing that it says "no" is the forking-paths problem
  the registration exists to prevent; the next study would switch back when that suited it.
- **Record an amendment, dated and marked as written after the results.** `config/experiments/preregistration.toml`
  has one: from the next study on, superiority needs the bootstrap interval above zero *and*, below 10 changed
  tasks, an exact McNemar p under 0.05.
- **Keep the registered decision, and say plainly what it rests on.** `retry` is kept under the original rule; the
  memo and the eval report both state that it would fail the amended one, and recommend confirming it on more
  tasks. A reader then knows exactly how strong the last step is.

[Self-Refine](https://arxiv.org/abs/2303.17651) (Madaan et al.) studies the general pattern of a model critiquing
and revising its own output.

### Prompt caching

Every MediaDoctor call starts with the same thousand tokens: the tool definitions and the system prompt. Prompt
caching lets the API keep that prefix: the first request writes it to a cache (at 1.25 times the input price), and
later requests that start with the same bytes read it (at 0.05 times the input price for Sonnet 5.5, 0.1 times for
Haiku 5.5), for five minutes after the last use. You opt in by marking the end of the prefix:

```python
system = [{"type": "text", "text": PROMPTS["v3"], "cache_control": {"type": "ephemeral"}}]
```

The cached prefix is everything up to the marker, in the order tools, system, messages, so anything that varies
(the user's question, a timestamp) must come after it, and the prefix must reach the model's minimum length (512
tokens for Sonnet 5.5 and Haiku 5.5). Usage then reports `cache_creation_input_tokens` and
`cache_read_input_tokens` separately from `input_tokens`. The details are in
[Anthropic's prompt caching guide](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) and the prices
in the [pricing page](https://platform.claude.com/docs/en/about-claude/pricing); `config/models.toml` holds the values
checked against both.

Caching does not change what the model sees, so it should not change a single answer. That makes it the one
experiment whose rule is "no change": the graded answers must be identical.

```text
  v3-cache  vs v3        +0.019 [+0.000, +0.046]  only parent  0, only v3-cache  2  cost/success -59%
```

Every graded answer is the same; the two extra successes are tasks that timed out under v3 and finished under
v3-cache. Cost per success fell 59%, and v3's extra few-shot tokens are now almost free, because they sit in the
cached prefix. The 76% in the cache column is the share of input tokens read from the cache.

Two caveats belong in any write-up. Caching pays only when requests arrive faster than the cache expires: exercise 4
shows a single call per cache lifetime costs 13% more than no caching. And for evals you run yourself, the
[Batch API](https://platform.claude.com/docs/en/build-with-claude/batch-processing) halves the price of every token
(the discounts stack) in exchange for results within 24 hours: right for a nightly suite, wrong for a user waiting.

### Latency: percentiles and timeouts

Latency adds up along the trace, so the trace tells you where it went. `uv run mediadoctor-lab11 latency retry`
splits each task's time into agent calls, self-check calls, and tools, and lists the tasks that slowed most;
exercise 2 uses it to explain why the retry configuration's p95 rose by 2.7 s while its p50 rose by 0.7 s (the
slowest 5% are all retried tasks). The general lessons:

- **Calls in sequence add up; the tail compounds.** A task with three calls in a row is slow if any one is slow.
  Dean and Barroso's [The Tail at Scale](https://research.google/pubs/the-tail-at-scale/) explains why
  tail latency, not median latency, dominates systems that combine many steps.
- **Output tokens are the slow part.** Each generated token costs time; input tokens are much cheaper, and cached
  input cheaper still. A shorter answer format is a latency lever. Anthropic's
  [reducing latency guide](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency)
  lists the others (smaller models, shorter prompts and outputs, streaming).
- **Set the timeout from the user, then count timeouts as failures.** The Google SRE book's chapter on
  [service level objectives](https://sre.google/sre-book/service-level-objectives/) explains why to set targets on
  percentiles rather than averages.

## Step 5: the frontier, and choosing a point on it

Plot success against cost per task: `uv run mediadoctor-lab11 pareto --svg runs/m11/pareto.svg`.

![MediaDoctor success against cost per task, with 95% intervals; the Pareto frontier joins haiku, cascade, v3-cache, and retry](pareto.svg)

A configuration is on the **Pareto frontier** when no other is both cheaper and more accurate. Here that is Haiku,
the cascade, v3 with caching, and retry. v1, v2, and v3 without caching are dominated: v3-cache beats each of them
on both axes, so there is never a reason to choose them. The frontier does not tell you which of its points to
choose; that is a business question (what is a correct answer worth to you, and what is a wrong one?). It does
tell you which questions are worth asking.

Two traps when reading it:

- **Point estimates make the frontier look sharper than it is.** "The cheapest configuration within 2 points of the
  best" is retry itself on point estimates, and no configuration can be shown to be within 2 points of it once
  you use the paired intervals (exercise 1). With this dev set, a 2-point tolerance is below what you can measure.
- **The x-axis is cost per task, not per success**, so that accuracy is not counted twice. Read cost per success off
  the report for the headline.

The lab applies the pre-registered rule mechanically: each change is kept only if it passed its own test and its
parent was kept, and the recommendation is the most accurate kept configuration. That gives
v1 → v2 → v3 → v3-cache → retry: success from 67% to 90% and cost per success from $0.0088 to $0.0043 (−51%).
Both numbers are measured on the dev queries every step was chosen on. Five sequential keep-or-drop decisions on the
same 108 queries favour changes that happened to do well on them, so the chain's total gain is optimistic: the
held-out look below is the estimate to lead with, and the dev chain is the record of how you got there.

## Step 6: knowing when to stop

Stop optimizing, or at least stop this round, when one of these is true:

- **The next gain is below what you can measure.** With 11 failures left in 108 dev tasks, a fix that removes a
  third of them is a 3-point gain, and seeing it reliably takes about 300 tasks (exercise 5). Without more data, you
  would be tuning to noise.
- **The remaining failures are not worth their cost.** If every remaining task succeeded, cost per success would
  fall another 10%. Compare that with the engineering time and the added latency of the next idea.
- **The dev set is being used up.** Every round of "look at dev, change, re-run" fits the system a little to those
  108 queries. When the held-out result starts trailing dev, refresh the dev set from production (modules 4 and 9).
- **The failure taxonomy has changed.** After a big improvement, re-run error analysis. The top modes are now
  different, and the old ranking is stale.

The opposite mistake is stopping because a number looks good. A success rate with no interval, or measured on the
cases you tuned against, does not count.

## Step 7: communicating the result

Three documents, for three readers.

**The experiment log** is for your team and your future self. One entry per experiment: date, the one change, the
hypothesis and expected effect, the decision rule, the measured result with its interval, and the decision.
Write the first half before the run. The [template](../../eval-templates/experiment-log.md) has the fields;
`uv run mediadoctor-lab11 log` renders the lab's log from `config/experiments/log.toml` plus the measurements.
Failed experiments stay in the log: E4 and E5 are as useful as E3, because they stop the next person from running
them again.

**The decision memo** is for the person who decides: one page, the decision requested in the first line, the
recommendation with three numbers (success, cost per success, p95), the options considered, how sure you are, what
you are not claiming, and next steps. `uv run mediadoctor-lab11 memo` drafts it from the numbers;
the [template](../../eval-templates/decision-memo.md) explains each section. Edit the draft: a generated memo is a
starting point, and you are the one who signs it.

**The eval report** (module 12's [template](../../eval-templates/eval-report.md)) is the reference behind the memo:
data, evaluators, full results, risks.

**Honest uncertainty** means every number that drives the decision comes with its interval and its n; the memo says
how small a difference the data can detect; and the thinnest step in the chain is named ("the retry gain rests on
five tasks; read it as likely, not proven").

**What not to say:**

- "90% accurate." Say "90% of 108 dev questions (95% CI 83% to 94%); production questions differ."
- "Haiku is worse." Say "Haiku lost 21 points on this agent, prompt, and question mix."
- "No regression." Say "no difference we could detect; this test can see differences of about 8 points."
- "Caching halves cost." Say "at our traffic, where the cache stays warm, cost per success fell 59%."
- "Statistically significant" on its own. Say what the interval is, and what decision it supports.

## Worked example: "route easy questions to Haiku and cache the prompt"

Here is a proposal you will hear in some form on every LLM team: *send the easy questions to the small model and
cache the long system prompt, and the bill halves without hurting quality.* It sounds like one change. It is two,
and the lab tests them separately.

**Caching, by itself.** Take query m4q002 (a false premise about AV1 on the atlas-a1), whose run is not the first in
its batch, so the cache is warm. The first call of each run, from the traces:

```text
v3        input 1,052 uncached               output 75   $0.002854   (1,052 x $2 + 75 x $10) / 1M
v3-cache  input    39 uncached + 1,029 read  output 75   $0.000931   (39 x $2 + 1,029 x $0.10 + 75 x $10) / 1M
```

The 1,029-token prefix now costs about a hundredth of a cent per call instead of a fifth of a cent, and the output
tokens have become the largest part of the cost. Across the dev set, cost per success falls 59%, every graded answer is identical, and p95 does not get worse.
The first half of the proposal is true, and it is the half that needed no quality trade-off at all.

**Routing, by itself.** The cascade sends every question to Haiku first and escalates to Sonnet when Haiku's answer
fails a code check. Its success is 15.7 points lower than v3-cache (CI −23.1 to −9.3), far outside the 5-point
margin. The failure modes say why: Haiku's wrong answers mostly adopt the user's false premise or contradict the
tool output, and those answers are well formed and properly cited, so the router passes them. The second half of
the proposal fails, for a reason that tells you what to build next (a router that can see those modes).

**What goes in the memo.** Not "we halved the bill": "caching cut cost per successful task by 59% with no change to
any answer; routing to Haiku with code-check escalation lost 16 points and is rejected; a judge-based router is
the next experiment." Then the full chain: with the v2 and v3 prompts and a retry on judge failure, success rose
from 67% to 90% while cost per success fell 51%. Before anything ships, the recommended configuration gets its one
look at the held-out split:

```text
$ uv run mediadoctor-lab11 confirm retry --release
held-out (n=29): v1 0.828  retry 0.966 [0.828, 0.994]  paired diff +0.138 [+0.000, +0.310]
cost/success $0.00650 -> $0.00329; look logged in runs/m11/holdout_log.csv
```

Consistent with dev, and wide, as 29 tasks must be. It is the only estimate of the gain that was not used to choose
the configuration, so the eval report leads with it (+0.138 [+0.000, +0.310]) and quotes the dev chain's +0.231 as
the optimistic, selection-biased number it is. Its interval reaching zero is the honest summary: the direction is
clear, the size is not.

## Checklist

- [ ] The fix was chosen by expected value from the failure taxonomy, with the guesses written down.
- [ ] Each configuration differs from its parent in one thing; combined changes have an ablation.
- [ ] The primary metric, guardrails, margin, and decision rule were written before the first run.
- [ ] Experiments run on dev; the held-out split is read once, by the chosen configuration, and the look is logged.
- [ ] Comparisons are paired on the same queries; the discordant counts are reported.
- [ ] The minimum detectable difference was checked before the run.
- [ ] Every report has success with a CI, p50 and p95 latency, timeouts counted as failures, cost per task, and cost
      per successful task.
- [ ] Few-shot examples come from failures outside the eval set and are checked for near-duplicates.
- [ ] Caching was verified to change no answer; its savings are stated for the traffic that keeps it warm.
- [ ] Cascades and retries are reported with their router or judge accuracy and their latency cost.
- [ ] The experiment log keeps failed experiments; the decision memo fits on one page and avoids the claims above.

## Summary

Cost per successful task is the number to optimize, measured alongside task success with an interval and latency at
p50 and p95. Choose fixes by expected value from the failure taxonomy, change one thing at a time, and decide by a
rule written down first, on a dev set, with one held-out look before release. On MediaDoctor, two prompt changes
aimed at the top failure modes raised success from 67% to 83%; prompt caching then cut cost per success by 59%
without changing any answer; Haiku alone and a code-check cascade were far cheaper but lost 16 to 21 points; and a
self-check with one retry added 4.6 points for 6% more cost per success and 2.7 s at p95. The recommended
configuration is 51% cheaper per success than the release and 23 points more accurate, with the thinnest step named
in the memo. Stop when the next gain is below what your data can measure, or worth less than it costs.

Next: [Module 12](../12-capstone/index.md) puts the whole course together in a capstone eval report.

Continue with the [lab](lab.md), the [exercises](exercises.md), and the [quiz](quiz.md).
