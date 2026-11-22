# 9. Production monitoring and a custom annotation app

**Goal:** keep measuring after release, notice when the traffic or the agent changes, and turn what you find in
production into labelled cases for the next round.

**Estimated time:** 8 hours (lesson 2 h, lab 4 h, exercises and quiz 2 h)

By the end of this module you will be able to:

- say what an online eval can and cannot do that an offline one can, and which evaluators belong where;
- sample production traces at random, by stratum, and by signal (thumbs-down, retries, slow responses, tool errors,
  failed checks), and still estimate a pass rate correctly from a biased queue;
- run cheap code checks on every request and an LLM judge on a sample, and correct the judge's rate for its known
  errors;
- detect drift in the inputs (topics, devices), in the outputs and metrics (p-charts and CUSUM), and around model
  snapshot changes, and tell the three apart;
- read explicit and implicit user feedback for what it is: sparse, biased, and still useful as a pointer;
- review traces in a keyboard-driven annotation app built for this agent, measure agreement between two annotators
  with Cohen's kappa, and promote reviewed traces into golden-dataset candidates.

Artifacts: the annotation app (`labs/annotate`, `uv run annotate serve`), the monitoring dashboard (the app's
`/dashboard` page and `uv run mediadoctor-lab09 monitor`), labels v2 (`data/labels/production_modes_v2.toml`, with the
new `unknown-device-guess` mode), the new `evalkit.monitor` module and `evalkit.annotate.kappa_report`, the lab CLI
(`uv run mediadoctor-lab09`), and the [monitoring cheat sheet](../../cheatsheets/monitoring.md).

## Intuition: a field-trial dashboard and a bug-triage tool you wrote yourself

When a player or a codec ships to millions of devices, the lab results stop being the whole story. You watch field
telemetry: crash rates by build, decoder fallbacks by SoC, rebuffering by network type. You do not read every
session; you sample, and you pay extra attention to sessions that crashed, retried, or took too long. When a new
phone shows up in the device mix, you notice before anyone files a bug, because the dashboard is split by device.
And when someone does file a bug, the triage tool that helps most is rarely the generic one. It is the internal page
that shows the `ffprobe` output, the decoder that was picked, and the logcat lines around the stall on one screen.

Production evals are the same job. Offline evals (modules 5 to 8) answer "is this version good on the cases we
chose?". Production asks two other questions: "are the cases we chose still the cases users bring?" and "did
something change that our cases cannot see?". You answer them with cheap checks on everything, judges on a sample,
drift charts, and a queue of traces that people read. Reading is still the core activity, so the reading tool matters:
generic trace viewers show generic spans, while a small app that renders this agent's probe output, decoder lists,
and logcat next to the answer turns a two-minute review into a fifteen-second one. This module builds that app.

## Step 1: online and offline evals

| | Offline (modules 5 to 8) | Online (this module) |
|---|---|---|
| Inputs | a fixed golden set you chose | whatever users send, today |
| Labels | reviewed in advance | none at first; you sample and label |
| When | before a change ships, in CI | continuously, after it ships |
| Good at | comparing versions on the same cases; gating | noticing new inputs, new failures, and changes you did not make |
| Blind to | inputs you did not think of | anything you do not sample or log |

Both use the same evaluators, at different volumes. A rule of thumb that the lab follows:

- **Code checks on all traffic.** They are free, deterministic, and fast: format, citations that point at real
  evidence (module 5's `check_evidence_is_real`), and "investigated before answering". Every request gets them.
- **Judges on a sample.** A judge call costs money and time, and its verdict has known errors (module 5). Run it on a
  random fraction, and report its rate with the judge-error correction from module 6.
- **People on a smaller, targeted sample.** The annotation queue. Human labels are the only ones that can find a
  failure mode nobody has named yet.

Things you did not change also change in production: the provider updates a model snapshot, an app release changes
what users ask, a new phone appears. Online evals are how you find out. Hamel Husain and Shreya Shankar's FAQ answer on
[how evaluations differ between CI and production](https://hamel.dev/blog/posts/evals-faq/how-are-evaluations-used-differently-in-cicd-vs-monitoring-production.html)
makes the same split.

## Step 2: the simulated week

The lab replays one week of MediaDoctor traffic: Monday 16 to Sunday 22 November 2026 (IST), 776 requests from 176
users. Each request replays a recorded trace (module 3's 100 traces of the released prompt, plus 40 new AV1 traces
recorded for this module) with its own request id, time, user, app version, model snapshot, latency, and feedback.
Two events are planted, and the lab's job is to find them from the data:

| When (IST) | Event | What it does |
|---|---|---|
| Tue 17, 14:00 | the provider's model snapshot changes (`claude-sonnet-5-5-20261001` to `-20261116`, fictional ids) | nothing, by construction |
| Thu 19, 10:00 | app 4.2 starts a staged rollout (15%, then 40%, 70%, and 90% of users) that makes AV1 the default codec | 70% of 4.2 requests ask about AV1, many on a new phone, the `vela-v2`, which has no device profile |

!!! info "Synthetic-authored traffic"
    The traffic, the feedback, the 40 AV1 traces, their reference labels, the judge verdicts on them, and the two
    annotators' labels were written for this module by `scripts/author_module09_fixtures.py` and are labelled
    `"source": "synthetic-authored"`. Module 3's traces are replayed many times each, so "776 requests" is really 140
    distinct traces in different contexts. Everything the lab reports (the charts, alarms, queues, estimates, and
    agreement) is computed from those files.

Because every request carries a known label, the lab can show the truth next to each estimate. In production you
would not have that column; that is the point of the rest of the module.

## Step 3: sampling production traces

You cannot read 776 traces a week, let alone 776,000. Four ways to choose, all in `evalkit.monitor`:

- **Random.** Each request with probability `rate`, decided by a hash of its id (`stable_fraction`), so the same
  request is always in or out and the sample is reproducible. Random is the only sample whose failure rate estimates
  the population's, and the only one that can surface a failure nothing flags.
- **Stratified.** A few requests from every stratum (here, every topic), so rare topics are not drowned out by
  common ones.
- **Signal-triggered.** Every request with a signal: a failed code check, a thumbs-down, a tool error, a retry (the
  same user asking the same thing within ten minutes), or a slow response (above the reference window's p95,
  6,355 ms). These find failures fast, but only the kinds that set off a signal.
- **Judge-triggered.** Judge-failed requests, or (exercise 1) requests where the judge and the other evidence
  disagree.

The FAQ answer on [sampling production traces](https://hamel.dev/blog/posts/evals-faq/how-can-i-efficiently-sample-production-traces-for-review.html)
orders these from exploratory to targeted and recommends keeping some random traces in every batch; the lab's queue
does exactly that. `lab09.queue()` builds it in four moves:

1. take every signalled request (probability 1), a 5% random sample, and 3 requests per topic;
2. fold identical traces together (same fingerprint: same question, tool calls, and answer), keeping a count;
3. order triggered items by signal (failed check first, then thumbs-down, tool error, retry, slow);
4. interleave: two triggered items, then one random or stratified item, so a reviewer never reads a long run of
   failures and starts expecting them.

**A biased queue gives a biased rate.** The queue exists to find failures, so it is full of them. Read naively, it
says the week fails 55% of the time. The truth is 34%. Each item was picked with a known probability, so weight each
label by one over that probability (the Horvitz-Thompson idea, in its ratio form, the Hajek estimator:
`evalkit.monitor.weighted_rate`):

| Estimate of the week's failure rate | Value |
|---|---|
| truth (simulation only) | 0.340 |
| the queue, unweighted (275 picks) | 0.553 |
| the queue, weighted by 1/p | 0.364 |
| the random part only (30 picks) | 0.400 |

The weighted queue uses every label and lands close to the truth; the random part alone is unbiased but noisy at
n=30. Never report a pass rate from a triggered queue without weights.

## Step 4: code checks on everything, a judge on a sample

The code checks run on all 776 requests and cost nothing. The online judge is module 5's tool-grounding judge (v2),
run on a 30% random sample (232 requests; it applies to 229 of them, where a tool succeeded). Its validation on
module 5's test split gave TPR 0.90 and TNR 0.60 on 25 labelled traces, and module 6's bootstrap gives the
corrected rate:

| Period | n | Judge's pass rate | Corrected [95% CI] | Truth (simulation only) |
|---|---|---|---|---|
| before the rollout | 132 | 0.864 | 0.927 [0.576, 1.000] | 0.932 |
| after the rollout | 97 | 0.680 | 0.561 [0.000, 0.894] | 0.784 |

Three lessons sit in this table.

- **For change detection, the raw rate is enough.** The same judge on both sides of the rollout dropped from 0.864
  to 0.680. Whatever its errors, they did not change on Thursday morning; the traffic did.
- **For the level, the correction needs more labels than you have.** With 25 validation traces, only 5 of them
  failing, the TNR is uncertain and the corrected interval covers almost everything. The point estimate after the
  rollout (0.561) is further from the truth than the raw rate. Label more failing traces before quoting a corrected
  number; module 6's advice on validation size applies here with force.
- **The judge's errors can drift too.** On the 40 new AV1 traces its TPR is 0.79 (27 of 34 passing answers passed)
  and its TNR 1.00, against 0.90 and 0.60 on the validation set. New traffic is exactly where a judge's validation is
  least relevant: re-validate on a labelled sample of the new traffic (the queue gives you one).

## Step 5: drift

"Drift" covers three different things, and the response differs:

| Drift | What moved | How the lab sees it | Typical response |
|---|---|---|---|
| Input | what users ask | topic shares by day, PSI against the reference window; new device names | add cases to the golden set; check coverage |
| Output and metric | what the agent does | p-chart and CUSUM on the code checks' failure rates; judge rate | read the traces behind the change |
| System | the model, prompt, or tools | the model snapshot attribute on every trace; before/after comparison | treat it as a release you did not make |

**Input drift.** A small rule-based tagger (`tag_topic`, `tag_device`) puts each question into one of the golden
set's topics and extracts the device name. Topic shares against Monday to Wednesday give a population stability
index (PSI; above 0.1 is "worth a look", above 0.25 is a real shift):

| Day | Requests | AV1 share | Topic PSI | New devices | App 4.2 share |
|---|---|---|---|---|---|
| Mon 16 | 121 | 20.7% | 0.039 | | 0% |
| Tue 17 | 126 | 21.4% | 0.017 | | 0% |
| Wed 18 | 125 | 21.6% | 0.023 | | 0% |
| Thu 19 | 133 | 31.6% | 0.114 | vela-v2 | 17% |
| Fri 20 | 131 | 67.2% | 1.031 | vela-v2 | 79% |
| Sat 21 | 74 | 74.3% | 2.242 | vela-v2 | 91% |
| Sun 22 | 66 | 77.3% | 2.083 | vela-v2 | 92% |

A tagger is a classifier with its own errors. The lab's rules score 1.000 on the week's own questions (they were
written while looking at them) and 0.835 on module 4's questions they never saw. Validate a tagger on held-out
questions, like any other evaluator, before trusting a PSI built on it.

**Metric drift: control charts.** A p-chart (the NIST handbook's
[attribute control charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc332.htm)) plots each day's
failure rate against limits of three standard errors around the reference rate, so a small day gets wider limits.
The `evidence_fail` check (an answer cites evidence the trace does not contain) has a reference rate of 1.3%: Monday
to Wednesday are inside the limits; Thursday (4.5%, limit 4.3%) and every day after are above.

Daily charts are slow: they wait for a day to end. **CUSUM** (cumulative sum; E. S. Page, 1954) accumulates evidence
request by request. For a 0/1 stream with reference rate p0, each request adds the log-likelihood ratio of "the rate
is now p1" against "it is still p0", the sum never goes below zero, and the alarm fires when it crosses h. With
p1 = 2·p0 and h = 4:

| Metric | p0 | Alarm (IST) | After the rollout |
|---|---|---|---|
| tool_error | 8.9% | Thu 19, 14:57 | +5.0 h |
| evidence_fail | 1.3% | Fri 20, 05:42 | +19.7 h |
| thumbs_down | 3.8% | none | |
| format_fail | 0.8% | none | |

Choosing h is a trade between false alarms and delay; exercise 2 measures both on replayed traffic. The thumbs-down
rate never alarms: Step 6 explains why.

**System drift: model snapshots.** Every trace records `gen_ai.response.model`. When it changes, compare the 24 hours
on each side: `evidence_fail` went from 1/125 to 3/115 (p = 0.27). The test cannot see a change that small, and here
there was none (the simulation makes the snapshot change harmless), but you cannot know that from 240 requests. Treat
a snapshot change like a release you did not make: re-run the offline gate from module 8 against the new snapshot,
where the paired comparison has the power that a before/after comparison of different traffic lacks.

**Segments find the cause.** Split the metrics after the rollout by app version: version 4.1.3 has 0% evidence
failures and 8.9% tool errors; 4.2.0 has 16.1% and 40.8%. The drift is not "the model got worse"; it is "4.2 users ask
questions the agent cannot answer well".

## Step 6: human feedback, explicit and implicit

| Signal | Kind | Fired | Precision | Recall |
|---|---|---|---|---|
| failed code check | automatic | 60 | 1.00 | 0.23 |
| tool error | automatic | 150 | 0.60 | 0.34 |
| retry (same question within 10 min) | implicit | 32 | 0.72 | 0.09 |
| thumbs-down | explicit | 34 | 0.71 | 0.09 |
| slow (above the reference p95) | implicit | 48 | 0.44 | 0.08 |
| thumbs-up | explicit | 32 | 0.16 (as a pass signal: 0.84) | |
| copied the answer | implicit | 216 | 0.31 (as a pass signal: 0.69) | |

Precision is "of the requests it flagged, how many failed"; recall is "of the failing requests, how many it
flagged". The week's true failure rate is 34%.

Explicit feedback has three biases that the lab models on purpose (exercise 4 measures them):

- **Sparse and self-selected.** 40 of 176 users rated anything, and 8.5% of requests carry a thumb. The thumbs-down
  rate (4.4%) says almost nothing about the failure rate (34%).
- **Confidence hides failures.** A confident, wrong answer about the `vela-v2` gets fewer thumbs-down (5.6%) than an
  ordinary failure (10.4%), and about as many thumbs-up as a correct answer. Users can only punish failures they can
  see.
- **Annoyance is not failure.** Slow but correct answers get thumbs-down twice as often as fast correct ones.

Implicit signals (retries, copies, abandonment) are plentiful but ambiguous: a copy might mean "useful" or "I will
paste this into a bug report to show how wrong it is". Use all of these to choose what to read, not as the metric.
The FAQ answer on
[surfacing problematic traces beyond user feedback](https://hamel.dev/blog/posts/evals-faq/how-do-i-surface-problematic-traces-for-review-beyond-user-feedback.html)
makes the same case.

## Step 7: the annotation app

`labs/annotate` is a small FastAPI app with server-rendered HTML and [HTMX](https://htmx.org/docs/) for the
swaps: about 800 lines of Python, 230 of templates, and 50 of JavaScript for the keys. It reads any trace store in
the course's span format, a queue, and a failure-mode taxonomy, and writes labels as CSV.

![The review screen: the queue position and why the trace was picked, the trace tree, the agent's answer with each
citation checked, the tool outputs rendered for this domain, and the label form](../../assets/m9/review.webp)

What makes it faster than a generic viewer:

- **Domain rendering.** A `probe_media` result is a compact stream table, `codec_caps` is a decoder list, `read_logcat`
  is log lines with errors highlighted, and a failed tool call is a red box with its error. Citations in the answer
  are marked green if the trace contains them and red if it does not, so fabricated evidence is visible at a glance.
- **Context up front, noise hidden.** The header shows why the trace is in the queue (its signals or stratum), how
  many identical requests it stands for, the app version, device, and model. The raw attributes are behind `c`.
- **Keyboard first.** `p`/`f` for the verdict, `1` to `9` to toggle failure modes, `m` to name a new mode, `n` for a
  note, `g` to flag it as a golden candidate, Enter to save and load the next trace (an HTMX swap, no page load), `j`
  and `k` to move, `?` for help. Every form also works as a plain POST without JavaScript.
- **Bounded sessions.** A progress bar and "next unlabelled" keep a session to the queue in front of you.
- **Exports that feed the rest of the course.** Labels in `evalkit`'s annotation CSV, the failure taxonomy CSV
  (modes ranked by count and severity, module 3's format), golden-dataset candidates as JSONL, and the golden flags.

The FAQ answers on [building a custom annotation tool](https://hamel.dev/blog/posts/evals-faq/should-i-build-a-custom-annotation-tool-or-use-something-off-the-shelf.html)
and [what makes a good review interface](https://hamel.dev/blog/posts/evals-faq/what-makes-a-good-custom-interface-for-reviewing-llm-outputs.html)
describe these features and argue for building your own; the app is one small instance of that advice.

The app binds to 127.0.0.1, has no login and keeps no secrets, and writes only into its output directory. Before
putting it on a shared server you would add authentication, and production traces would need the privacy review
that real user data deserves.

**Two annotators, and Cohen's kappa.** When two people label the same traces, their raw agreement overstates how much
they agree, because some agreement happens by chance. Cohen's kappa (Cohen, 1960) corrects for it:
κ = (p_o − p_e) / (1 − p_e), where p_o is the observed agreement and p_e the agreement expected if each labelled at
random with their own rates. The lab's two annotators labelled the first 40 queue items:

![The agreement page: overall kappa, per-mode kappa, and the traces where the annotators differ](../../assets/m9/agreement.webp)

| | Agreement | p_e | Kappa |
|---|---|---|---|
| verdict (pass/fail) | 0.95 | 0.60 | 0.87 |
| unknown-device-guess | 1.00 | 0.65 | 1.00 |
| fabricated-evidence | 0.88 | 0.61 | 0.68 |
| vague-next-step | 0.95 | 0.90 | 0.48 |

The last row is the rare-category paradox: 95% agreement, but a mode tagged once or three times in 40 traces has an
expected agreement of 0.90, so kappa is modest. Read kappa per mode, with the counts, and fix the definitions where it
is low; the agreement page lists the disputed traces so an alignment session can start from them. Shreya Shankar et
al.'s [Who Validates the Validators?](https://arxiv.org/abs/2404.12272) describes how reviewers' criteria shift as
they see more outputs; two-annotator checks are one way to catch that.

## Step 8: closing the loop into the golden datasets

Production review is only worth its cost if it changes something. The loop:

1. **Name new failure modes.** Reviewing the queue surfaces a mode the taxonomy did not have:
   `unknown-device-guess`, where `codec_caps` fails for an unknown device and the agent describes its decoders
   anyway. Labels v2 adds it (severity 3).
2. **Write a check for it if you can.** This one is detectable in code (exercise 5): a failed `codec_caps` call plus
   an answer that names the device without admitting the data is missing. It finds every labelled case on the source
   traces (precision 0.94, one borderline case) and costs nothing to run on all traffic.
3. **Promote traces to golden candidates.** `close_loop` turns failing or flagged labels into candidates with a
   proposed split (by hash: 20% test, 25% dev, the rest train), folds repeats of the same question, and flags near-duplicates of
   existing golden questions (Jaccard similarity of 3-word shingles of 0.35 or more). From annotator A's 40 labels: 28 candidates, 9 of
   them for the new mode, 2 near-duplicates to decide on.
4. **Review, then version.** Candidates go into `data/golden/` only after a person reads them, and then the golden
   manifest version is bumped (module 8). Re-validate any judge whose criteria the new mode touches.

## Worked example: the AV1 week

The syllabus asked for one story; here it is from the data.

- **Monday to Wednesday** are quiet. Code-check failure rates are inside their limits, topic PSI is below 0.04, and
  the model snapshot change on Tuesday afternoon shows 1/125 versus 3/115 evidence failures: no evidence of a change.
- **Thursday 10:00:** app 4.2 starts rolling out. By 14:57 the tool-error CUSUM alarms (+5.0 h). The day's topic PSI
  reaches 0.114 and a device nobody has seen, `vela-v2`, appears. The day ends above the p-chart limit.
- **Friday:** AV1 questions are 67% of traffic (PSI 1.03); the evidence-failure CUSUM alarms at 05:42. The online
  judge's pass rate is down from 0.864 to 0.680. Split by app version, 4.1.3 is unchanged and 4.2.0 fails.
- **The queue** puts the week's failures in front of a reviewer, interleaved with random and per-topic picks. In the
  first 40 items, 9 are confident answers about the `vela-v2`'s decoders after `codec_caps` returned "unknown
  device": a failure the taxonomy has no name for. The reviewer adds `unknown-device-guess` with `m`.
- **Thumbs-down** never alarms: confident wrong answers do not look wrong to users.
- **Annotator B** labels the same 40 traces; kappa is 0.87 on verdicts and 1.00 on the new mode, so the definition is
  clear enough to hand to a judge or a check.
- **The fix path:** a code check for the new mode (it would have flagged 78 requests this week), 28 golden
  candidates with proposed splits, and a note for the agent's next prompt: when a device has no profile, say so and
  ask for its decoder list.

![The monitoring dashboard: daily rates with the reference window, CUSUM alarms, drift by topic, and the judge's
corrected rates](../../assets/m9/dashboard.webp)

## Checklist

- [ ] Code checks run on all traffic; judges on a random sample with a stated rate; people on a queue.
- [ ] The queue mixes signal-triggered, random, and stratified picks, folds duplicates, and records each pick's
      probability.
- [ ] Rates from the queue are weighted by 1/p; nobody quotes an unweighted queue rate.
- [ ] Judge rates are reported raw for change detection and corrected (with an interval) for levels; the judge is
      re-validated on new traffic.
- [ ] Input drift (topics, devices), metric drift (p-chart, CUSUM), and system drift (model snapshot) each have a
      chart and an alert rule, tested on replayed traffic for false alarms and delay.
- [ ] Metrics can be split by app version, device, and model snapshot.
- [ ] User feedback picks traces to read; it is never the quality metric.
- [ ] The review tool renders this agent's data, runs from the keyboard, and exports labels, a taxonomy, and golden
      candidates.
- [ ] When two people label, kappa is reported per mode with counts, and low-kappa modes get clearer definitions.
- [ ] New failure modes reach the taxonomy, a check or judge, and the golden set, through a reviewed, versioned
      change.

## Summary

Offline evals tell you whether a version is good on the cases you chose; production tells you whether those are
still the right cases. Run free checks on everything, judges on a sample with their errors accounted for, and put a
mixed, weighted queue in front of people with a tool that makes reading fast. Watch inputs, outputs, and the system
separately, with alert rules you have tested for false alarms. Treat user feedback as a pointer with known biases.
And close the loop: every new failure mode found in production should end up as a label, a check, and a golden case.

Next: [the lab](lab.md), then the [exercises](exercises.md) and [quiz](quiz.md). The
[monitoring cheat sheet](../../cheatsheets/monitoring.md) collects the rules and commands.
