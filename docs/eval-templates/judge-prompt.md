# Template: binary LLM judge prompt

Used from module 5 onward with the `judge` model from `config/models.toml`. One judge per failure mode.

```text
You are evaluating answers from MediaDoctor, an assistant for Android and multimedia engineers.

Criterion: <ONE failure mode, stated as what a PASS looks like>

PASS means: <precise definition>
FAIL means: <precise definition, including borderline cases you have decided are FAIL>

Examples:
<input, output, critique, verdict>   (2 to 4 examples, including at least one FAIL and one tricky PASS)

Now evaluate:
<question>{question}</question>
<context>{retrieved_context}</context>
<answer>{answer}</answer>

First write a short critique explaining your reasoning, then the verdict.
Respond as JSON: {"critique": "...", "verdict": "PASS" | "FAIL"}
```

**Checklist before you trust it**

- [ ] Labels from a domain expert on at least 100 cases, split into train (examples), dev (iterate), and test (report once)
- [ ] TPR and TNR reported on the test split
- [ ] Criteria revisited after labeling (definitions tend to drift as you grade)
- [ ] Prompt and model ID versioned; fixtures recorded
