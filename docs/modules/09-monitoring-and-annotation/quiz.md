# Quiz

Eight questions on sampling, online evals, drift, and annotation. Answer each, then expand to check.

**1. Your review queue takes every thumbs-down and tool error plus a 5% random sample. After labelling it, 5.8% of
the queue failed. A manager asks for the week's failure rate. What do you report?**

??? question "Answer"
    Not 5.8%: the queue was built to over-represent failures. Weight each label by one over its inclusion
    probability (1 for triggered picks, 1/0.05 = 20 for random ones) and report the weighted rate (the Hajek
    estimator), with an interval. In the lab that turns 0.058 into 0.040 [0.010, 0.096] against a true 0.033. The
    random part alone is also unbiased but noisier. The unweighted rate is only useful for "how productive was the
    queue".

**2. Why keep random picks in a queue at all, when triggered picks find failures several times faster?**

??? question "Answer"
    Two reasons. Triggered picks only find failures that set off a signal you already have; a random sample is the
    only way to meet a failure nothing flags (in the lab, the week's failures are unsupported details in otherwise
    correct answers: no code check or tool error fires on them, and thumbs-down catches an eighth). And
    random picks give an unbiased estimate of the overall rate, and a check on the signals' recall. Interleaving them
    also keeps reviewers from expecting every trace to fail.

**3. Which evaluators run on all production traffic, which on a sample, and why?**

??? question "Answer"
    Code checks (format, real citations, investigated before answering, detectors for known modes) on everything:
    they are free, fast, and deterministic. LLM judges on a random sample at a stated rate: they cost money and add
    latency, and their errors have to be corrected anyway, which needs only a sample. People on a smaller, targeted
    queue, because only people can name a new failure mode.

**4. Across a rollout that sent tool errors from 0% to 36% of the new version's requests, the online judge's pass
rate stays at 1.000, and the lab prints no judge-corrected rate. Does that show the rollout changed nothing? Why is
there no corrected rate?**

??? question "Answer"
    No. A judge measures its own criterion (here, ignoring tool output) and nothing else: the change this week was
    in what users ask and which tools fail, and the week's failures are of another mode, so an unchanged judge rate
    is what you would expect either way. There is no corrected rate because the judge's validation set has 28
    traces and all of them pass: its TNR is undefined, so the correction cannot be computed, and a 1.000 pass rate
    is equally consistent with a perfect agent and a judge that passes everything. Label failing traces for its
    criterion (from the queue, and from the new traffic) and re-validate before quoting a level; when the raw rate
    does move, it is still fair evidence of a change, because the same judge scored both periods.

**5. The provider changes the model snapshot on Tuesday. Evidence failures are 0/123 the day before and 0/115 the
day after (p = 1.00). Your colleague says "no regression". What is the better statement, and what would you run?**

??? question "Answer"
    "No evidence of a change at this sample size", which is not the same thing: with 0 failures in 115 requests the
    new rate could still be as high as about 3/115 (2.6%, the rule of three), and a before/after comparison of 238
    different requests cannot see a change of a couple of points. Treat the snapshot change like a release you did
    not make: re-run the offline gate (module 8) on the golden set against the new snapshot, where a paired
    comparison on the same cases has far more power. Keep the snapshot id on every trace so you can split by it.

**6. You set a CUSUM on slow responses with p1 = 2·p0. With h = 2 it fired on Tuesday, two days before the rollout;
with h = 6 it fired 29 hours after. How do you choose h?**

??? question "Answer"
    Measure both costs on replayed traffic: the false-alarm rate on weeks with no change (resample the reference
    window) and the delay on a known change. Pick the h whose false-alarm rate the on-call person can live with (in
    the lab, about 0.20 a week at h = 4, 0.09 at h = 5) and accept the delay that comes with it; route lower
    thresholds to a dashboard rather than a pager. Re-tune when traffic volume changes, because false alarms per
    week grow with volume. And check the reference window has events in it: for tool errors, which never happened
    before the rollout, the replay reports 0 false alarms for every h, which says nothing about the rule.

**7. An annotator agrees with the reference labels on 95% of verdicts (38 of 40), but kappa is 0.48. One colleague
says kappa is a bad metric; another says they do not agree. Who is right?**

??? question "Answer"
    Neither entirely. Failures are rare (3 of 40 in the reference, 1 for the annotator), so two raters who almost
    always say "pass" agree 90% of the time by chance; kappa measures agreement beyond that, and two disputed traces
    use up most of the remaining room. Report kappa with the counts, read the disputed traces (in the lab, both are
    correct answers with an unsupported aside), and sharpen the definition. For a rare category it may also be
    better to collect more examples (a targeted queue) before measuring agreement at all. And note that the lab's two
    annotators agree with each other perfectly (kappa 1.00) on the same 40 traces: agreement between raters shows
    consistency, not correctness.

**8. Name three things that make a custom annotation app faster than a generic trace viewer, and one thing it must
not do.**

??? question "Answer"
    Any three of: rendering the domain's data in its own form (probe output as a stream table, decoder lists, logcat
    with errors highlighted, citations marked as found or missing); showing why the trace is in the queue and its
    context (app version, device, model) up front, with raw attributes hidden; driving everything from the keyboard
    with a save-and-next that does not reload the page; showing progress through a bounded queue; and exporting
    straight into the formats the rest of the workflow uses (labels, taxonomy, golden candidates). It must not leak
    data: no secrets in it, bound to localhost unless it has authentication, and real user traces only after a
    privacy review.
