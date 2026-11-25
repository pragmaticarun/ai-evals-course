# Quiz

Eight questions on replay fixtures, gating, and dataset hygiene. Answer each, then expand to check.

**1. Why does the eval gate run in replay mode in CI instead of calling the model?**

??? question "Answer"
    Replay is deterministic, free, fast, and needs no API key in CI, so the same commit always gets the same verdict
    and a failure means the change, not the weather. The price is that the suite can only evaluate requests that were
    recorded: any change to a request is a miss that has to be recorded deliberately, read, and labelled. Live calls
    belong in a separate, manual or scheduled job with the key held as a secret.

**2. A PR rewords one sentence of the system prompt and the gate exits with "needs re-recorded fixtures". The author
suggests marking the gate as optional for prompt-only changes. What do you say?**

??? question "Answer"
    No: a prompt change is a behaviour change, and the gate is right that it has no evidence about the new prompt.
    Record the gate set (locally with a key or with the live-evals workflow), read the flips, label the answers that
    changed, bump the golden manifest, rewrite the baseline, and push. If prompt tweaks are frequent, make recording
    cheap and routine rather than making the gate optional.

**3. On 119 shared cases the baseline passes 1.000 of the citations check and the candidate 0.975: three cases
flipped from pass to fail, none the other way. A "no drop allowed" rule blocks. What does the paired gate do, and
why?**

??? question "Answer"
    It warns, and does not block. McNemar's test looks at the discordant cases: 3 against 0 is consistent with chance
    (p = 0.75 after the Holm adjustment across the tier), so the drop (0.025), although above the 0.02 minimum
    effect, is not shown to be real. But the 95% interval (−0.059 to 0.000) reaches below the −0.05 margin, so the
    run cannot rule out a drop you would care about: that is a warn. The three flipped cases are listed in the
    report, so a reviewer can read them (here, each cites a KB document that was never retrieved).

**4. Why does the gate read the baseline from the base branch rather than from the pull request?**

??? question "Answer"
    So a pull request cannot move its own goalposts. If the gate compared with the PR's copy, a PR could rewrite the
    baseline to match its own (worse) behaviour and pass. The PR must still commit a new baseline that matches its
    behaviour, so that after merging, `main`'s baseline describes what `main` ships; the diff of that file shows
    reviewers exactly which cases changed.

**5. The judge tier on 30 dev cases passes all three judges on both prompts with no flips at all, yet the human
labels fail one of the candidate's dev answers (a KB citation without a search). Name two reasons the judge tier is
weak here.**

??? question "Answer"
    Sample size: 30 cases with the 12% disagreement the code tier measures between the same two prompts cannot
    reliably see any drop smaller than that, and with no disagreement in the judge tier itself there is no estimate
    of its noise at all. Judge error: the tool-grounding judge passed the answer the humans failed, and because no dev
    trace failed in module 5, the judges' TNR on dev could not even be measured, so "every judge passes" says little
    about whether failures are absent. Gate on code checks (the citations check caught this case); use the judge tier
    for information until the judge and n are good enough.

**6. Which of these must be in the golden manifest, and why: the dataset file, the reference labels, the judge specs,
the recorded fixtures, the workflow YAML?**

??? question "Answer"
    Everything the gate's numbers depend on: the dataset, the labels, the judge specs (they define what a judge
    verdict means), and the recorded fixtures (they are the outputs being scored). Any of them changing changes the
    numbers, so it should fail CI until the version is bumped. The workflow YAML changes how and when the suite runs,
    not what it measures, so it belongs in code review, not in the golden set.

**7. A teammate mines "the 20 worst cases" across all labelled data every week and iterates the prompt on them. What
goes wrong, and what would you change?**

??? question "Answer"
    The held-out cases are among the labelled data, so the prompt is being tuned on them: the held-out number stops
    being an honest estimate, and overfitting goes undetected. Restrict mining to the gate and train splits (make the
    script go through `HoldoutGuard`, or add a check like exercise 2's to `evals/`), log every held-out look, and
    rotate fresh cases into the held-out split once it has been looked at too often.

**8. The hygiene check reports that a held-out question shares an eight-word sentence with one of a judge's few-shot
examples. Is that leakage? What are the options?**

??? question "Answer"
    It is contamination of the judge, not of the agent: the judge has seen a near-copy of that case's framing with a
    verdict attached, so its accuracy on that case (and the held-out TPR and TNR) may be inflated. Options: replace
    the example with one from another scenario (which changes every judge request, so re-record and re-validate the
    judge), drop the case from the held-out split (bump the golden version), or accept it with a recorded reason and
    revisit at the next judge revision. What you should not do is ignore it: record the decision, as
    `data/golden/hygiene_review.csv` does.
