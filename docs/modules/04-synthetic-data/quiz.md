# Quiz

Eight questions. Answer each, then expand to check.

**1. Why generate tuples first and queries second, instead of asking a model for 200 test questions?**

??? question "Answer"
    Because the two steps are different problems. Choosing *what* to test is a coverage problem that code solves
    exactly (every pair, every small slice, no impossible combinations). Writing *how* a person says it is a language
    problem, and a model does it well when each call has one concrete situation. A single "give me 200 questions"
    prompt mixes the two, and the model falls back on one kind of question phrased many ways.

**2. What makes a good dimension? Give one that is not.**

??? question "Answer"
    It is one kind of variation, it has a few concrete values you can write a query for, and changing it plausibly
    changes whether the system succeeds (it comes from a failure hypothesis). "Difficulty" is a poor dimension: it
    mixes expertise, evidence, and ambiguity, so a failure on a "hard" query does not tell you what made it hard.

**3. Pairwise coverage covers all 242 feasible value pairs with 34 tuples. What does it not guarantee?**

??? question "Answer"
    It does not cover combinations of three or more values, and it does not give any slice more than one or two
    examples. A failure that needs `novice` + `missing-detail` + `log` together may be absent, and one example per pair
    cannot tell you a failure rate. That is why the course adds a stratified fill to 200 after the pairwise set.

**4. Uniform random sampling of 50 tuples gave audio-focus 3 tuples and AV1 12. Why, and what is the fix?**

??? question "Answer"
    Uniform sampling is uniform over *valid tuples*, and audio focus has far fewer valid tuples than AV1 (the rules
    allow it only `evidence=none`, while AV1 has files, devices, and both). Small slices get few samples by
    construction. Fix: stratify by the dimension you care about (here, topic) so each value gets a similar count,
    or guarantee pair coverage first.

**5. Your synthetic queries score lower on distinct-2 (unique bigrams) than the 50 naive ones. Are they less
diverse?**

??? question "Answer"
    Not in the way that matters. Distinct-n measures word variety, and short generic sentences have few repeats. The
    structured queries repeat file names, device names, and pasted log lines on purpose, while covering every topic,
    persona, expertise level, and ambiguity type. Measure coverage of your dimensions, look at openings and LLM-style
    tells, and read a sample; do not use a single lexical diversity score as the target.

**6. Why does near-duplicate detection ignore pasted logcat lines, and why does it only compare queries with the
same `evidence` and `ambiguity`?**

??? question "Answer"
    Two different questions that paste the same log excerpt would otherwise look highly similar and one would be
    dropped. And two queries with nearly the same prose can be different test cases: one pastes the log (does the
    agent read it?) and one only mentions it (does the agent ask?). The tuple decides which queries may be
    duplicates; text similarity decides which ones are.

**7. What is leakage in a synthetic dataset, and how does the lab prevent it?**

??? question "Answer"
    A test (held-out) query that is a near-copy of a train or dev query, so improving on train quietly improves on
    test and the held-out score overstates generalisation. The lab groups queries whose similarity is at least 0.35
    and assigns each group to one split by hash, then checks with `leakage_pairs` (0 for v1; 46 if each query is
    split independently).

**8. On the dev slice, 9 of 18 false-premise queries fail. Can you report "MediaDoctor fails on half of the false
beliefs users bring"?**

??? question "Answer"
    No. The tuples were spread evenly on purpose, so the share of false-premise questions, and which premises appear,
    reflect your choices, not your users. The result says the agent *has* this failure mode and roughly how
    reliably it triggers on these premises. How often it hurts real users needs real traffic. Synthetic data finds
    and targets failures; it does not measure their frequency.
