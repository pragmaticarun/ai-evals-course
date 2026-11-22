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
Which numbers would have misled you, and why?

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.judge import confusion
    from mediadoctor import lab05

    dev, test = lab05.likert_scores("dev"), lab05.likert_scores("test")
    human_dev = lab05.human_pass("vague-next-step", list(dev))
    human_test = lab05.human_pass("vague-next-step", list(test))


    def binarise(scores, t):
        return {c: s >= t for c, s in scores.items()}


    # Choose the threshold on dev only.
    best = max((3, 4, 5), key=lambda t: confusion(human_dev, binarise(dev, t)).agreement)
    print(f"best threshold on dev: score >= {best}")
    for split, scores, human in (("dev", dev, human_dev), ("test", test, human_test)):
        print(f"{split:<4} likert>={best}: {confusion(human, binarise(scores, best))}")
    for split in ("dev", "test"):
        print(f"{split:<4} binary:    {lab05.validate('next-step', None, split).result}")

    assert best == 3
    assert confusion(human_test, binarise(test, best)).tnr == 0.0
    ```

    Output:

    ```text
    best threshold on dev: score >= 3
    dev  likert>=3: n=37 (human pass 33, fail 4)  TPR 1.00 (33/33)  TNR 0.75 (3/4)  agreement 0.97
    test likert>=3: n=29 (human pass 25, fail 4)  TPR 1.00 (25/25)  TNR 0.00 (0/4)  agreement 0.86
    dev  binary:    n=37 (human pass 33, fail 4)  TPR 0.97 (32/33)  TNR 0.75 (3/4)  agreement 0.95
    test binary:    n=29 (human pass 25, fail 4)  TPR 0.92 (23/25)  TNR 1.00 (4/4)  agreement 0.93
    ```

    On dev, "PASS if score >= 3" agrees with the labels on 97% of traces, better than the binary judge. On test the
    same threshold agrees on 86% and catches **none** of the 4 failures (TNR 0.00): every vague next step scored 3
    or 4 on test. The binary judge keeps TNR 1.00 (4/4).

    What went wrong: the scale has no agreed meaning between 2, 3, and 4, so the judge's scores for "partly
    actionable" drift between splits, and the threshold you fitted to one split's drift does not transfer. Agreement
    hides it because most traces pass. The fix is not a better threshold but a better question: write down what
    makes a next step actionable (names an API, a setting, a measurement, or the specific information to send) and
    ask for PASS or FAIL against that. If you want to see gradual progress, track several such binary criteria.

## Exercise 3: Show how judge error moves a pass rate, and why the interval is wide

1. A judge has TPR 0.9 and TNR 0.6. The true pass rate of the traffic is 0.70. What pass rate does the judge
   report? Check that `corrected_pass_rate` recovers 0.70.
2. The lab's corrected estimate has a 95% interval of about [0.24, 1.00]. Explain why, and show how the interval
   would change with 4 and 16 times as many labelled test traces (assume the extra traces behave like the ones
   you have).

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.judge import bootstrap_corrected, corrected_pass_rate
    from mediadoctor import lab05

    # 1. Inflation: a judge with TPR 0.9 and TNR 0.6 on traffic whose true pass rate is 0.70.
    true, tpr, tnr = 0.70, 0.9, 0.6
    observed = true * tpr + (1 - true) * (1 - tnr)
    print(f"observed {observed:.2f} for a true rate of {true:.2f}")
    assert round(observed, 2) == 0.75
    assert abs(corrected_pass_rate(observed, tpr, tnr) - true) < 1e-9

    # 2. Why the course's interval is so wide, and what more labels would do.
    est, _, test = lab05.estimate()
    spec = lab05.load_spec("tool-grounding")
    test_run = lab05.validate("tool-grounding", None, "test")
    labelled = [(test_run.human[c], bool(v.passed)) for c, v in test_run.verdicts.items()]
    unl = [
        bool(v.passed)
        for v in lab05.run_spec(spec, list(lab05.m3_items()), pool=lab05.m3_items()).values()
    ]
    print(f"25 labelled ({test.tn + test.fp} failures): CI [{est.low:.2f}, {est.high:.2f}]")
    for k in (4, 16):
        # Pretend each labelled trace had k independent twins with the same outcome. This is a
        # thought experiment about sample size, not something to do with real data.
        narrower = bootstrap_corrected(labelled * k, unl, draws=1000, seed=5)
        print(f"{25 * k} labelled ({5 * k} failures): CI [{narrower.low:.2f}, {narrower.high:.2f}]")
        assert narrower.high - narrower.low < est.high - est.low
    ```

    Output:

    ```text
    observed 0.75 for a true rate of 0.70
    25 labelled (5 failures): CI [0.24, 1.00]
    100 labelled (20 failures): CI [0.56, 1.00]
    400 labelled (80 failures): CI [0.65, 1.00]
    ```

    1. Observed = 0.70 × 0.9 + 0.30 × (1 − 0.6) = 0.63 + 0.12 = 0.75. The judge passes 40% of the bad answers, so
       the dashboard shows 75% when the truth is 70%. The judge's 10% false fails pull the other way, but there are
       fewer bad answers than good ones, so the false passes win. Correcting divides out both:
       (0.75 + 0.6 − 1) / (0.9 + 0.6 − 1) = 0.35 / 0.5 = 0.70.
    2. The denominator TPR + TNR − 1 is the judge's informativeness. With 5 labelled failures, the bootstrap often
       draws resamples where TNR is 0.2 or 0.4, the denominator gets close to 0, and the corrected rate swings to
       the extremes. Uncertainty about TNR, not about the traffic, dominates. With 20 labelled failures the lower
       bound rises to about 0.56, and with 80 to about 0.65. (The upper bound stays at 1.00 because the estimate is
       clipped and the point estimate is high.) The lesson: **label failures, not just traces**. If failures are
       rare, oversample them for labelling (from judge-failed or signal-flagged traces), since TNR is estimated
       only from them.

## Exercise 4: Validate a code check, then fix it

`check_investigated` has TNR 0.75 (3 of 4) against the `skipped-investigation` labels. Find the trace it misses,
explain why the check passed it, and write a better check. Measure the new one on all 137 traces.

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.judge import confusion
    from mediadoctor import lab05

    rows = {r["id"]: r for r in lab05.label_rows()}
    ids = list(lab05.items())
    human = lab05.human_pass("skipped-investigation", ids)


    def old(cid):
        return lab05.check_investigated(lab05.traces()[cid], rows[cid])


    missed = [c for c in ids if not human[c] and old(c)]
    print("missed:", missed, rows[missed[0]]["evidence"], lab05.items()[missed[0]].question[:60])


    def investigated_v2(cid):
        """Some investigation happened (any tool, including search_kb), or the agent asked for details."""
        it = lab05.items()[cid]
        return bool(it.tools) or bool(lab05.ASKS.search(it.answer))


    for name, fn in (("v1", old), ("v2", investigated_v2)):
        print(name, confusion(human, {c: fn(c) for c in ids}))
    assert confusion(human, {c: investigated_v2(c) for c in ids}).agreement == 1.0
    ```

    Output:

    ```text
    missed: ['m4q039'] none customer report - audio from our app continues over incoming
    v1 n=137 (human pass 133, fail 4)  TPR 1.00 (133/133)  TNR 0.75 (3/4)  agreement 0.99
    v2 n=137 (human pass 133, fail 4)  TPR 1.00 (133/133)  TNR 1.00 (4/4)  agreement 1.00
    ```

    The missed trace is an audio-focus question with `evidence=none`: nothing to inspect with ffprobe, codec_caps,
    or logcat, so the old check returned True without looking. But the agent did not search the knowledge base
    either; it answered from memory and cited `[kb:audio-focus]` without retrieving it. The expert's definition of
    "skipped investigation" was "did not look anything up", while the check's was "did not inspect the named
    evidence".

    The new check passes a trace if any tool ran (including `search_kb`) or the agent asked for details, and
    agrees with all 137 labels. Two cautions: 4 failures is a small validation set for a check too; and a
    deterministic check can still encode the wrong definition, so it needs labels just like a judge does, though
    only once rather than after every model update.

## Exercise 5: Diagnose the false-premise judge

On dev, the false-premise judge has TNR 0.44 (4 of 9). Group its disagreements, decide what a v2 should change,
and choose few-shot examples for it from the train split.

??? success "Solution"
    ```python
    # exercise-solution
    from collections import Counter

    from evalkit.judge import disagreements
    from mediadoctor import lab05

    v = lab05.validate("false-premise", None, "dev")
    labels = lab05.annotations()
    rows = {r["id"]: r for r in lab05.label_rows()}
    kinds = Counter()
    for cid, kind in disagreements(v.human, {k: x.passed for k, x in v.verdicts.items()}):
        if kind.startswith("judge PASS"):
            # Where did the agent use the false premise? With ignored-tool-output it is in the cause.
            where = "cause" if "ignored-tool-output" in labels[cid].modes else "next step"
            kinds[f"missed, premise used in the {where}"] += 1
        else:
            kinds[f"false alarm, {rows[cid]['ambiguity']} question"] += 1
    for k, n in kinds.most_common():
        print(f"{n}  {k}")

    # A train example of the missed kind, to add as a few-shot FAIL in false-premise v2:
    train_next = [
        c
        for c in lab05.ids_in("train")
        if "accepted-false-premise" in labels[c].modes and "ignored-tool-output" not in labels[c].modes
    ]
    print("train candidates:", train_next)
    assert kinds["missed, premise used in the next step"] == 5
    ```

    Output:

    ```text
    5  missed, premise used in the next step
    1  false alarm, false-premise question
    1  false alarm, missing-detail question
    train candidates: ['m4q073', 'm4q176']
    ```

    All five misses are answers that used the false premise in the **Next step** rather than in the cause, for
    example the audio-focus answers that recommend `AudioFocusRequest` "available from API 21" (it needs API 26).
    The judge's critiques say so themselves: "The answer does not repeat the user's claim in its cause". The v1
    FAIL definition says "repeats it or builds its cause or next step on it", but both FAIL examples show the
    premise in the cause, and the examples won.

    A v2 would add one sentence to FAIL ("this includes a next step that relies on the claim, such as an API level
    the user gave"), and one train example of exactly this kind: `m4q176` (the same audio-focus premise) or
    `m4q073` (`Display.isHdr()` from API 21). Check it with `leakage_problems`, rerun on **dev**, and read the
    disagreements again. The two false alarms are a separate issue (the judge failed an answer that does say "That
    premise does not hold here"), worth one PASS example if they persist. The test split has been used for v1; a
    v2 needs new test labels before you can report it.
