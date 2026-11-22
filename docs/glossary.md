# Glossary

Seeded in module 1; each later module adds its terms. The module that introduces a term is in brackets.

**Analyze, measure, improve** [1]
: The eval loop: find and name failures, build evaluators you trust for them, change the system and verify the change. Then repeat.

**Case / test case** [1]
: One input to the system (here, a user question) with an id, plus any metadata needed to evaluate it.

**Case set / dataset** [1]
: A fixed, versioned collection of cases. Comparisons are only meaningful on the same case set.

**Code check** [1]
: A deterministic evaluator written as code: an assertion, regex, schema validation, or lookup.

**Eval** [1]
: Any repeatable procedure that measures some aspect of a system's output quality over a set of cases.

**Failure mode** [1]
: A specific, named way the system goes wrong, for example "drops citations" or "retrieval missed the relevant document".

**Fixture (recorded response)** [1]
: A saved model response, stored under the SHA-256 hash of the exact request, so runs can be replayed offline.

**Ground truth / label** [1]
: A human judgment of whether an output is acceptable, made by someone who knows the domain.

**LLM-as-judge (model judge)** [1, 5]
: An LLM prompted to grade another model's output against a specific criterion. Trust it only after validating it against labels.

**Per-case diff** [1]
: The list of cases that changed from pass to fail (broken) or fail to pass (fixed) between two runs.

**Record / replay / live mode** [1]
: The three `evalkit.llm` modes: call the API and save the response, return saved responses offline, or call without saving.

**Regression** [1]
: A case that passed before a change and fails after it.

**Retrieval miss** [1, 7]
: The retriever did not return the document needed to answer, so downstream steps fail through no fault of their own.

**Root cause (first upstream failure)** [1, 3]
: The earliest step in a run where something went wrong; fixing it often fixes later symptoms.

**Trace** [1, 2]
: A structured record of everything one run did: model calls, tool calls, retrieved context, timings, tokens.
