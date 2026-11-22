# Quiz

Ten questions. Answer each, then expand to check.

**1. MediaDoctor sometimes cites `[tool:ffprobe]` without having called ffprobe. Code check or LLM judge? Why?**

??? question "Answer"
    A code check. Whether a cited tool was called, and succeeded, is in the trace as data: compare the citations in
    the answer with the `execute_tool` spans. It is exact, free, and cannot drift. Use a judge only where deciding
    requires understanding the meaning of the text.

**2. Why one judge per failure mode instead of one "overall quality" judge?**

??? question "Answer"
    An overall judge mixes several failure modes, so a FAIL does not say what to fix, a fix to one mode barely moves
    its score, and it cannot be validated against mode-specific labels. Narrow judges are easier to define, to
    validate (one TPR and TNR per mode), and to act on.

**3. Why ask the judge for a critique before the verdict?**

??? question "Answer"
    It gives the model room to look at the evidence before committing, and it gives humans a reason to read when
    the judge disagrees with a label. A critique that quotes the words the verdict rests on shows whether the judge
    was wrong, the label was wrong, or the criterion was unclear.

**4. With PASS as the positive class, define TPR and TNR. Which one tells you whether the judge catches
failures?**

??? question "Answer"
    TPR: of the traces humans passed, the share the judge passed. TNR: of the traces humans failed, the share the
    judge failed. TNR measures catching failures, and it is usually estimated from far fewer traces than TPR.

**5. A judge agrees with human labels on 88% of traces. Is it a good judge?**

??? question "Answer"
    Not necessarily. If 85% of traces pass, a judge that always says PASS agrees 85% of the time and catches no
    failures. Report TPR and TNR with their counts; agreement alone hides a low TNR.

**6. What are the train, dev, and test splits for, in judge validation?**

??? question "Answer"
    Train: the pool you take few-shot examples from (and may read freely). Dev: where you measure each change to the
    judge and read disagreements. Test: held out, run once when you have stopped changing the judge, and reported.
    If you change the judge after looking at test, test is no longer a held-out estimate; you need new test labels.

**7. Your tool-grounding judge has TPR 0.90 and TNR 0.60, and reports a pass rate of 0.82 on new traffic. What is
the corrected pass rate, and why does it need an interval?**

??? question "Answer"
    (0.82 + 0.60 − 1) / (0.90 + 0.60 − 1) = 0.42 / 0.50 = 0.84 (Rogan-Gladen). TPR and TNR are estimates from a
    small labelled set (here 20 passes and 5 failures), so the correction is uncertain too; a bootstrap that
    resamples both the labelled set and the traffic gives an interval that includes the judge's uncertainty.

**8. Give two ways a judge prompt can leak evaluation data.**

??? question "Answer"
    Few-shot examples taken from the dev or test split; and reference material the judge would not have in
    production, such as the expected answer, the human verdict, or the reviewer's note for the case. Both make the
    measured TPR and TNR better than the judge you will actually run.

**9. What is criteria drift, and what should you do about it?**

??? question "Answer"
    Reviewers' criteria change as they grade outputs: seeing real cases sharpens or shifts what counts as a failure
    (Shankar et al., "Who Validates the Validators?"). Expect it: write first definitions, label a batch, revise;
    version judge specs and labels together; relabel affected dev and test traces when a definition changes, and log
    the decisions from alignment sessions.

**10. Name two judge biases from the literature and one defence for each.**

??? question "Answer"
    Position bias (preferring the answer in one slot when comparing two): judge both orders and keep only
    consistent results, or use single-answer binary judges. Verbosity bias (preferring longer answers): criteria
    about specific claims, with examples where a long answer fails. Self-preference (favouring text in the judge's
    own style): validate against human labels and consider a judge from a different model family for important
    criteria.
