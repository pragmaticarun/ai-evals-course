# Quiz

Eight questions on sampling, online evals, drift, and annotation. Answer each, then expand to check.

**1. Your review queue takes every thumbs-down and tool error plus a 5% random sample. After labelling it, 55% of
the queue failed. A manager asks for the week's failure rate. What do you report?**

??? question "Answer"
    Not 55%: the queue was built to over-represent failures. Weight each label by one over its inclusion
    probability (1 for triggered picks, 1/0.05 = 20 for random ones) and report the weighted rate (the Hajek
    estimator), with an interval. In the lab that turns 0.553 into 0.364 against a true 0.340. The random part alone
    is also unbiased but noisier. The unweighted rate is only useful for "how productive was the queue".

**2. Why keep random picks in a queue at all, when triggered picks find failures several times faster?**

??? question "Answer"
    Two reasons. Triggered picks only find failures that set off a signal you already have; a random sample is the
    only way to meet a failure nothing flags (in the lab, confident wrong answers barely trigger thumbs-down). And
    random picks give an unbiased estimate of the overall rate, and a check on the signals' recall. Interleaving them
    also keeps reviewers from expecting every trace to fail.

**3. Which evaluators run on all production traffic, which on a sample, and why?**

??? question "Answer"
    Code checks (format, real citations, investigated before answering, detectors for known modes) on everything:
    they are free, fast, and deterministic. LLM judges on a random sample at a stated rate: they cost money and add
    latency, and their errors have to be corrected anyway, which needs only a sample. People on a smaller, targeted
    queue, because only people can name a new failure mode.

**4. After a rollout, the online judge's pass rate drops from 0.864 to 0.680. The judge-corrected rate after the
rollout is 0.561 with a 95% interval of [0.000, 0.894]. Is the corrected number wrong? What do you do?**

??? question "Answer"
    It is honest: with 25 validation labels, only 5 of them failing, the judge's TNR is barely known, so the
    corrected level is too. The raw drop is still good evidence of a change, because the same judge scored both
    periods. Use the raw rates to detect the change, and before quoting a level, label more traces (especially
    failing ones, and especially from the new traffic, where the judge's TPR fell to 0.79) and re-validate.

**5. The provider changes the model snapshot on Tuesday. Evidence failures go from 1/125 the day before to 3/115 the
day after (p = 0.27). Your colleague says "no regression". What is the better statement, and what would you run?**

??? question "Answer"
    "No evidence of a change at this sample size", which is not the same thing: a before/after comparison of 240
    different requests cannot see a change of a couple of points. Treat the snapshot change like a release you did
    not make: re-run the offline gate (module 8) on the golden set against the new snapshot, where a paired
    comparison on the same cases has far more power. Keep the snapshot id on every trace so you can split by it.

**6. You set a CUSUM on tool errors with p1 = 2·p0. With h = 2 it fired on Wednesday, before the rollout; with h = 6
it fired 22 hours after. How do you choose h?**

??? question "Answer"
    Measure both costs on replayed traffic: the false-alarm rate on weeks with no change (resample the reference
    window) and the delay on a known change. Pick the h whose false-alarm rate the on-call person can live with (in
    the lab, about 0.32 a week at h = 4, 0.12 at h = 5) and accept the delay that comes with it; route lower
    thresholds to a dashboard rather than a pager. Re-tune when traffic volume changes, because false alarms per
    week grow with volume.

**7. Two annotators agree on 95% of traces about whether `vague-next-step` applies, but kappa is 0.48. A says kappa
is a bad metric; B says they do not agree. Who is right?**

??? question "Answer"
    Neither entirely. The mode is rare, so two people who almost always say "no" agree 90% of the time by chance;
    kappa measures agreement beyond that, and a couple of disputed traces use up most of the remaining room. Report
    kappa with the counts, read the disputed traces, and sharpen the definition. For a rare mode it may also be
    better to collect more examples (a targeted queue) before measuring agreement at all.

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
