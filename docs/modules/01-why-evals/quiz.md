# Quiz

Eight questions. Answer each in your head (or on paper), then expand to check.

**1. Why are exact-match assertions on prose usually the wrong tool for LLM outputs?**

??? question "Answer"
    Many different strings are equally correct, so exact match fails good answers. Assert on properties that
    must hold (format, citations, forbidden content) instead.

**2. Put the three steps of the eval loop in order, and say what each produces.**

??? question "Answer"
    Analyze (named, ranked failure modes from reading real outputs), measure (evaluators you trust, with numbers
    and uncertainty), improve (changes backed by before and after results). Then back to analyze.

**3. True or false: an LLM judge is a good first evaluator for "the answer cites a document that exists".**

??? question "Answer"
    False. It is a set-membership test. Code checks are free, instant, and exactly right; save judges for fuzzy
    criteria.

**4. In the worked example, v2 fixed the two answers it targeted. Why was it still the wrong change?**

??? question "Answer"
    It broke three answers that previously passed (it dropped the `Sources:` line), and overall it went from 16/20
    to 15/20. Only a fixed case set with a per-case diff makes that visible.

**5. q05 passes all three code checks. What does that tell you about code checks?**

??? question "Answer"
    They verify shape, not truth. Factual consistency needs reading outputs, and later a judge validated
    against human labels.

**6. In replay mode, what happens if you change the model ID in `config/models.toml`?**

??? question "Answer"
    Every request hash changes, so replay raises `FixtureMissingError` and tells you to re-record. That is by
    design: a silent fallback would compare against the old model's answers.

**7. Who should define what a "good" MediaDoctor answer is?**

??? question "Answer"
    The domain expert or product owner, someone who knows multimedia debugging and the users, working with the
    engineer. Judges are later validated against that person's labels.

**8. q11 failed because retrieval returned the wrong documents. Which module's techniques would you use to (a) find failures like this systematically and (b) measure retrieval directly?**

??? question "Answer"
    (a) Error analysis, module 3: find the first upstream failure in each trace. (b) Retrieval evals in module 7:
    recall@k and MRR on a retrieval set.
