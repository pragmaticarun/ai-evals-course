# Self-assessment

The capstone has a self-assessment instead of a quiz: eight questions about your own report and the whole course.
Answer each one about **your** report first, in writing; then expand to compare with what a reviewer would look for.

**1. Read your Decision requested aloud. Could someone act on it without reading the rest?**

??? question "Answer"
    It should name the action (ship, fund, stop, route), the thing acted on (a configuration, a team, a slice),
    and the alternative it replaces. "Approve `retry` in `config/release.toml` in place of `v1`" passes; "we
    evaluated several configurations and found promising results" does not. If the decision needs a caveat to be
    safe, the caveat goes in the same paragraph, not in section 8.

**2. Pick the largest number in your summary. What is its interval, and what would change your recommendation if
the truth were at the bottom of it?**

??? question "Answer"
    In the reference report, the bottom of +0.231 is +0.157, which still supports shipping, so the recommendation is
    robust to the interval. If the bottom of your headline interval would change the decision, your report must
    say so and the recommendation becomes conditional (more data, or a staged rollout with module 9's monitors).
    A headline whose interval you have never thought about is the most common weakness in eval reports.

**3. Which of your evaluators would you least like a stakeholder to ask about, and why?**

??? question "Answer"
    Usually the judge with the smallest validation set or the lowest TNR, because a low TNR means bad answers pass
    and your quality numbers are optimistic. In the reference report that is the tool-grounding judge (TNR 0.60 on
    5 failing traces; the corrected interval runs from 0.24 to 1.00). The honest response is in the report already:
    the corrected rate, its interval, and the plan to label more failures. An evaluator you cannot defend should
    not carry a headline number.

**4. Your slice has n queries. What is the smallest difference it can detect, and did your report claim anything
smaller?**

??? question "Answer"
    The report's slice section prints it (module 6's `mdd_paired`; for 12 to 15 queries, nothing smaller than the
    discordant share). Any claim about a slice-level improvement below that size is an anecdote, however it is
    worded. The useful output of a small slice is the list of surviving failures by id and a data request, not a
    rate.

**5. What did your evaluation not test that a user will meet in the first week?**

??? question "Answer"
    For MediaDoctor: real user phrasing (all queries are synthetic), devices outside the device table, logs and
    licence errors for DRM questions, non-English questions, load, and the production regression monitoring found.
    The report's Scope and Risks should list the ones that matter for the decision. If you cannot name any, you
    have not looked; module 9's production sample is where to look.

**6. Could a colleague reproduce your three summary numbers from your appendix alone, today?**

??? question "Answer"
    Only if the appendix has the exact command (with slice, date, and `--release` flag), the inputs fingerprint or
    git sha, and the ids of every trace you quote. The reference report's appendix is generated with the report, so
    it cannot go stale; a hand-written report needs the same discipline. Try it: clone your fork into a fresh
    directory and run the commands.

**7. Where in your report did you choose the analysis after seeing the data?**

??? question "Answer"
    Slice choice is the usual place: picking the topic that makes the candidate look best (or worst) and then
    reporting its p-value as if it had been chosen in advance. The reference report chooses its slice by a stated
    rule (the weakest topic under the candidate) and the lab asks you to write your expectation before looking.
    Other places: changing the success definition, dropping a configuration from a table, or reading the held-out
    split twice. Say what was pre-registered and what was exploratory; exploratory findings are fine when they are
    labelled.

**8. Across the whole course, which stage of the loop would you build first on a new LLM product, and which would
you skip?**

??? question "Answer"
    Build tracing (module 2) and error analysis on 100 traces (module 3) first: everything else depends on knowing
    your failure modes, and both are cheap. Add code checks before judges, and judges only for the modes code cannot
    see, validated before you trust them (module 5). Put intervals on every number from the start (module 6). A CI
    gate (module 8) and monitoring (module 9) come when the product has users; red-teaming (module 10) as soon as
    it reads untrusted input. Skip nothing, but do not build a judge for a mode you have seen twice, or an
    experiment your data is too small to read.
