# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: Fix a judge prompt that leaks the expected answer

A colleague "improved" the tool-grounding judge: they pasted the correct diagnosis for thumbnail crashes into the
FAIL definition ("so the judge knows what right looks like"), and added a vivid FAIL example, `m4q010`. Build their
version with `dataclasses.replace`, find every leak with `evalkit.judge.leakage_problems`, explain why each one
matters, and fix it.

??? success "Solution"
    ```python
    # exercise-solution
    import sys

    sys.path.insert(0, "scripts")
    from dataclasses import replace

    from module03_scenarios import S

    from evalkit.judge import Example, leakage_problems
    from mediadoctor import lab05

    spec = lab05.load_spec("tool-grounding")
    leaky = replace(
        spec,
        version="leaky",
        fail_def=spec.fail_def + " For thumbnail crashes the correct cause is: " + S["thumbs"]["cause"],
        examples=spec.examples + (Example("m4q010", "FAIL", "Contradicts the log."),),
    )
    splits = lab05.splits()
    references = [sc["cause"] for sc in S.values()]  # expected answers the judge must never see
    problems = leakage_problems(leaky, splits, references)
    for p in problems:
        print(p)
    assert len(problems) == 2

    # The fix: drop the reference answer and replace the test example with a train one.
    fixed = replace(leaky, fail_def=spec.fail_def, examples=spec.examples)
    assert leakage_problems(fixed, splits, references) == []
    print("fixed:", leakage_problems(fixed, splits, references))
    ```

    Output:

    ```text
    example m4q010 comes from split 'test', not train
    prompt contains reference text: 'Each visible thumbnail allocates its own c2.lumen.avc.decode'
    fixed: []
    ```

    Two leaks, two different harms:

    - **The expected answer in the prompt.** The judge no longer checks whether the answer agrees with the tool
      output; it checks whether the answer matches the reference diagnosis. On thumbnail questions it will look
      excellent on dev and test, because those labels were written from the same reference, and it will be useless
      on any new kind of question, or on a correct answer worded differently. In production there is no reference
      answer, so the judge you validated is not the judge you run.
    - **A test-split example.** `m4q010` is in the test split, so the judge is graded on a trace it was shown with
      the answer. Every test number for this judge is now optimistic, and the test split cannot be used to report
      on it again. (A dev example is less bad but still inflates the dev numbers you iterate on.)

    The fix is to remove both and pick a train trace if an extra example is needed. If the judge genuinely needs
    domain facts (for example, which API level added `AudioFocusRequest`), give it reference *notes* that would
    also be available in production, such as the knowledge-base document, not the expected answer for the case.

## Exercise 2: Turn a 1 to 5 judge into binary criteria and compare agreement

`mediadoctor-lab05 likert` runs a judge that scores how actionable the next step is, from 1 to 5. Choose the
threshold that best matches the human labels on dev, apply it to test, and compare with the binary next-step judge.
What can these numbers tell you, and what can they not?

??? success "Solution"
    ```python
    # exercise-solution
    from itertools import combinations

    from evalkit.synth import dedup, similarity
    from mediadoctor import lab04

    rows = lab04.generate_queries(lab04.make_tuples(lab04.load_default_space()))
    by_id = {r["tuple_id"]: r for r in rows}
    items = [(r["tuple_id"], r["query"]) for r in rows]


    def same_case(i):
        return tuple(by_id[i][k] for k in lab04.DEDUP_WITHIN)


    kept = {t: dedup(items, t, key=same_case) for t in (0.1, 0.15, 0.2, 0.3, 0.4, 0.6, 0.9)}
    for t, res in kept.items():
        print(f"threshold {t}: keep {len(res.kept)}")

    # The pairs a threshold could act on: the most similar queries within the same test case.
    pairs = sorted(
        (
            (similarity(qa, qb), a, b)
            for (a, qa), (b, qb) in combinations(items, 2)
            if same_case(a) == same_case(b)
        ),
        reverse=True,
    )
    print("\n--- the three most similar pairs ---")
    for s, a, b in pairs[:3]:
        print(f"{s:.2f} {a} {by_id[a]['persona']:<14} {by_id[a]['query'][:70]!r}")
        print(f"     {b} {by_id[b]['persona']:<14} {by_id[b]['query'][:70]!r}")

    assert [len(r.kept) for r in kept.values()] == [184, 195, 199, 200, 200, 200, 200]
    assert round(pairs[0][0], 2) == 0.20
    ```

    Output:

    ```text
    best threshold on dev: score >= 3
    dev  likert>=3: n=30 (human pass 30, fail 0)  TPR 1.00 (30/30)  TNR nan (0/0)  agreement 1.00
    test likert>=3: n=28 (human pass 28, fail 0)  TPR 1.00 (28/28)  TNR nan (0/0)  agreement 1.00
    dev  likert>=4: n=30 (human pass 30, fail 0)  TPR 0.97 (29/30)  TNR nan (0/0)  agreement 0.97
    test likert>=4: n=28 (human pass 28, fail 0)  TPR 1.00 (28/28)  TNR nan (0/0)  agreement 1.00
    dev  likert>=5: n=30 (human pass 30, fail 0)  TPR 0.53 (16/30)  TNR nan (0/0)  agreement 0.53
    test likert>=5: n=28 (human pass 28, fail 0)  TPR 0.82 (23/28)  TNR nan (0/0)  agreement 0.82
    dev  binary:    n=30 (human pass 30, fail 0)  TPR 1.00 (30/30)  TNR nan (0/0)  agreement 1.00
    test binary:    n=28 (human pass 28, fail 0)  TPR 1.00 (28/28)  TNR nan (0/0)  agreement 1.00
    share scored 5: dev 0.53, test 0.82
    ```

    No dev or test trace is labelled `vague-next-step`: every next step the agent wrote was judged actionable. So
    "agreement" here is just TPR, TNR is undefined (0/0) for every threshold and for the binary judge, and **no
    number in this table says whether either judge catches a vague next step.** Choosing "score >= 3" because it
    agrees 100% on dev is choosing the threshold that fails nothing; it would choose the same on traffic where half
    the next steps were vague.

    What the data does show is the scale drifting. All 58 next steps are acceptable to a human, yet the judge gives
    53% of the dev ones a 5 and 82% of the test ones. A threshold of 5 would fail 14 good answers on dev and 5 on
    test; a threshold fitted where such a move happens does not transfer, because nothing anchors what a 4 means
    against a 5. On data with real failures, the same drift can push vague answers above whatever threshold you
    fitted on dev, and the threshold would then catch none of them.

    The fix is not a better threshold but a better question: write down what makes a next step actionable (names
    an API, a setting, a measurement, or the specific information to send) and ask for PASS or FAIL against that.
    Then validate it on labelled **failures**; if your traffic has none, collect or write some before you trust the
    judge's TNR. If you want to see gradual progress, track several such binary criteria.

## Exercise 3: Show how judge error moves a pass rate, and why the interval is wide

1. A judge has TPR 0.9 and TNR 0.6. The true pass rate of the traffic is 0.70. What pass rate does the judge
   report? Check that `corrected_pass_rate` recovers 0.70.
2. Can the course's test split support a correction at all? Then, for a hypothetical labelled set with 5 failures
   (TPR 18/20, TNR 3/5) and traffic the judge passes 73 of 89 times, compute the corrected rate and its bootstrap
   interval, and show how the interval would change with 4 and 16 times as many labelled traces (assume the extra
   traces behave like the ones you have).

??? success "Solution"
    ```python
    # exercise-solution
    import math

    from evalkit.judge import bootstrap_corrected, corrected_pass_rate
    from mediadoctor import lab05

    # 1. Inflation: a judge with TPR 0.9 and TNR 0.6 on traffic whose true pass rate is 0.70.
    true, tpr, tnr = 0.70, 0.9, 0.6
    observed = true * tpr + (1 - true) * (1 - tnr)
    print(f"observed {observed:.2f} for a true rate of {true:.2f}")
    assert round(observed, 2) == 0.75
    assert abs(corrected_pass_rate(observed, tpr, tnr) - true) < 1e-9

    # 2a. The course's own test split cannot estimate TNR at all.
    test = lab05.validate("tool-grounding", None, "test").result
    print(f"course test split: {test}")
    assert test.tn + test.fp == 0 and math.isnan(test.tnr)

    # 2b. A hypothetical labelled set with 5 failures (TPR 18/20 = 0.90, TNR 3/5 = 0.60) and
    # hypothetical traffic the judge passes 73 of 89 times. These counts are made up for the
    # thought experiment; they are not course data.
    labelled = [(True, True)] * 18 + [(True, False)] * 2 + [(False, False)] * 3 + [(False, True)] * 2
    unl = [True] * 73 + [False] * 16
    base = bootstrap_corrected(labelled, unl, draws=1000, seed=5)
    print(f"25 labelled (5 failures): corrected {base.corrected:.2f}, CI [{base.low:.2f}, {base.high:.2f}]")
    assert round(base.corrected, 2) == 0.84
    for k in (4, 16):
        # Pretend each labelled trace had k independent twins with the same outcome.
        narrower = bootstrap_corrected(labelled * k, unl, draws=1000, seed=5)
        print(f"{25 * k} labelled ({5 * k} failures): CI [{narrower.low:.2f}, {narrower.high:.2f}]")
        assert narrower.high - narrower.low < base.high - base.low
    ```

    Output:

    ```text
    observed 0.75 for a true rate of 0.70
    course test split: n=28 (human pass 28, fail 0)  TPR 1.00 (28/28)  TNR nan (0/0)  agreement 1.00
    25 labelled (5 failures): corrected 0.84, CI [0.12, 1.00]
    100 labelled (20 failures): CI [0.57, 1.00]
    400 labelled (80 failures): CI [0.65, 1.00]
    ```

    1. Observed = 0.70 × 0.9 + 0.30 × (1 − 0.6) = 0.63 + 0.12 = 0.75. The judge passes 40% of the bad answers, so
       the dashboard shows 75% when the truth is 70%. The judge's 10% false fails pull the other way, but there are
       fewer bad answers than good ones, so the false passes win. Correcting divides out both:
       (0.75 + 0.6 − 1) / (0.9 + 0.6 − 1) = 0.35 / 0.5 = 0.70.
    2. The course's test split has no human failures for the tool-grounding mode, so TNR is 0/0 and the correction
       cannot be computed: there is nothing to say how often the judge passes a bad answer. With the hypothetical 5
       failures, the point estimate is (0.82 + 0.6 − 1) / 0.5 = 0.84, but the interval runs from about 0.12 to
       1.00. The denominator TPR + TNR − 1 is the judge's informativeness; with 5 failures, resamples often have
       TNR 0.2 or 0.4, the denominator gets close to 0, and the corrected rate swings to the extremes. Uncertainty
       about TNR, not about the traffic, dominates. With 20 labelled failures the lower bound rises to about 0.57,
       and with 80 to about 0.65. (The upper bound stays at 1.00 because the estimate is clipped and the point
       estimate is high.) The lesson: **label failures, not just traces**. If failures are rare, as they are in
       this course's data, oversample them for labelling (from judge-failed or signal-flagged traces), since TNR
       is estimated only from them.

## Exercise 4: Validate a code check, then fix it

`check_investigated` has TPR 0.78 (115 of 147) against the `skipped-investigation` labels: it fails 32 traces
that the expert passed. Find them, explain why the check failed them, and write a better check. Measure the new
one on all 147 traces, and say what the measurement cannot tell you.

??? success "Solution"
    ```python
    # exercise-solution
    from collections import Counter

    from evalkit.synth import assign_splits, leakage_pairs
    from mediadoctor.lab04 import GROUP_THRESHOLD, load_dataset

    v1 = load_dataset()
    items = [(r["tuple_id"], r["question"]) for r in v1]
    by_tid = {r["tuple_id"]: r for r in v1}

    grouped = assign_splits(items, salt="mediadoctor-v1", group_threshold=GROUP_THRESHOLD)
    naive = assign_splits(items, salt="mediadoctor-v1", group_threshold=1.01)  # no grouping
    for name, splits in (("grouped", grouped), ("independent", naive)):
        leaks = leakage_pairs(items, splits, GROUP_THRESHOLD)
        print(f"{name:<12} {dict(Counter(splits.values()))}  leaking pairs: {len(leaks)}")
    print(f"same assignment either way: {grouped == naive}")

    # Nothing reaches 0.35. Lower the bar to see the closest pairs that do cross splits.
    close = sorted(leakage_pairs(items, naive, 0.15), key=lambda x: -x[2])
    print(f"{len(close)} cross-split pairs at similarity >= 0.15:")
    for a, b, s in close:
        print(f"  {s:.2f} [{naive[a]}] {by_tid[a]['question'][:60]!r}")
        print(f"       [{naive[b]}] {by_tid[b]['question'][:60]!r}")
    assert len(leakage_pairs(items, grouped, GROUP_THRESHOLD)) == 0 and grouped == naive
    assert len(close) == 3
    ```

    Output:

    ```text
    32 false alarms; tools used: Counter({('search_kb',): 31, ('search_kb', 'search_kb'): 1})
    m4q003 device DRM playback is capped at a lower rendition on one of the bu
    v1 n=147 (human pass 147, fail 0)  TPR 0.78 (115/147)  TNR nan (0/0)  agreement 0.78
    v2 n=147 (human pass 147, fail 0)  TPR 1.00 (147/147)  TNR nan (0/0)  agreement 1.00
    ```

    The false alarms are mostly `missing-detail` questions (28 of the 32): the dataset row says there is a device,
    file, or log to inspect, but the question only says "one of the budget test phones" or "the log they sent".
    The agent searched the knowledge base, answered from it, and said what it had not checked ("I haven't inspected
    the asset (no file name given)"). The old check wants an inspecting tool, or a request matching its narrow
    `send me` / `which device` pattern, so it fails these. The expert's definition of "skipped investigation" was
    "did not look anything up and did not say what it could not check"; the check's was "did not run the tool the
    dataset expected".

    The new check passes a trace if any tool ran (including `search_kb`) or the agent asked for details, and
    agrees with all 147 labels. But read that 1.00 carefully: **no trace in this set is a human FAIL for
    skipped-investigation**, so TNR is 0/0 and a check that always returned True would also score 1.00. The labels
    show v2 stops the false alarms; they cannot show it still catches a real skipped investigation, and v2 is
    looser than v1 (a lone `search_kb` call now passes a question that pasted a log). Before trusting it, add
    labelled failures: traces where the agent answered an inspectable question without looking, written or
    collected for the purpose. A deterministic check can encode the wrong definition, so it needs labels just like
    a judge does, though only once rather than after every model update.

## Exercise 5: Diagnose the false-premise judge

On dev, the false-premise judge agrees with every label. Find out what that result rests on: how many dev
questions carry a false premise, what the judge did with them, and whether the train split offers a FAIL example
for a v2.

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.judge import disagreements
    from mediadoctor import lab05

    v = lab05.validate("false-premise", None, "dev")
    labels = lab05.annotations()
    rows = {r["id"]: r for r in lab05.label_rows()}
    print(v.result)
    dis = disagreements(v.human, {k: x.passed for k, x in v.verdicts.items()})
    print("disagreements:", dis)

    # Where could the judge have failed? On questions that carry a false premise.
    fp_dev = [c for c in v.verdicts if rows[c]["ambiguity"] == "false-premise"]
    print(f"{len(fp_dev)} dev questions with a false premise; judge passed {sum(v.verdicts[c].passed for c in fp_dev)}")

    # A FAIL few-shot example for v2 would have to come from train:
    by_split = {s: sum("accepted-false-premise" in labels[c].modes for c in lab05.ids_in(s))
                for s in ("train", "dev", "test")}
    print("accepted-false-premise labels by split:", by_split)
    assert dis == [] and len(fp_dev) == 12
    assert all(v.verdicts[c].passed for c in fp_dev)
    assert by_split == {"train": 0, "dev": 0, "test": 0}
    ```

    Output:

    ```text
    n=30 (human pass 30, fail 0)  TPR 1.00 (30/30)  TNR nan (0/0)  agreement 1.00
    disagreements: []
    12 dev questions with a false premise; judge passed 12
    accepted-false-premise labels by split: {'train': 0, 'dev': 0, 'test': 0}
    ```

    There is nothing to group: the judge has no disagreements on dev. Twelve dev questions carry a false premise
    (for example "AudioFocusRequest works from API 21", or "lumen-l3 decodes HEVC Main 10 in hardware"), the agent
    corrected every one, and the judge's critiques say so ("The answer corrects this to API 26+ from the knowledge
    base"). That is worth knowing: on these 12 the judge does not raise false alarms on an answer that pushes back
    on the user. It is TPR evidence only.

    No trace in any split was labelled `accepted-false-premise`, so TNR is undefined and the train split has no
    FAIL example to add; that is why every few-shot example in `false-premise.v1.toml` is a PASS. A v2 cannot be
    diagnosed from these labels. To validate the judge's TNR you need failing traces: collect them from real
    traffic, ask the agent the same false-premise questions under a weaker prompt or model, or write a few answers
    that accept the premise by hand (labelled as written, kept out of dev and test, or in a new test set). Check
    any new example with `leakage_problems`, rerun on **dev**, and read the disagreements. With data where the
    agent does accept premises, the method above is what would show whether the judge misses premises used in the
    Next step rather than in the cause.
