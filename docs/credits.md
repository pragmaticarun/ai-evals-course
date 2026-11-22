# Credits

This course is original work: the text, code, datasets, knowledge-base notes, and recorded fixtures were written
for it. Its overall arc and several core ideas come from the work of **Hamel Husain** and **Shreya Shankar**, and
anyone serious about evals should read them directly and consider their course.

## Where ideas come from

| Idea used here | Where it is used | Source |
|---|---|---|
| Course arc: build a measurable agent, error analysis, evaluators you trust, CI/CD, red-teaming, improving cost and accuracy | Whole course | [AI Evals For Engineers & PMs](https://maven.com/parlance-labs/evals) (Maven course by Hamel Husain and Shreya Shankar) |
| The analyze, measure, improve cycle | Module 1 onward | Hamel Husain and Shreya Shankar's course and [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) |
| Layering evaluators from cheap assertions up to human and model review | Module 1 | [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/), Hamel Husain |
| Looking at your data first; error analysis before metrics; custom data viewers | Modules 1, 3, 9 | [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/), Hamel Husain |
| Binary pass/fail judges aligned with a domain expert | Modules 1, 5 | [Using LLM-as-a-Judge For Evaluation](https://hamel.dev/blog/posts/llm-judge/), Hamel Husain |
| Validating evaluators against human labels; criteria drift | Modules 5, 6 | Shreya Shankar et al., [Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences](https://arxiv.org/abs/2404.12272) (arXiv 2404.12272) |

This course is independent and is not affiliated with or endorsed by Hamel Husain, Shreya Shankar, Parlance Labs,
Maven, or Anthropic.

## Tools

[uv](https://docs.astral.sh/uv/), [Zensical](https://zensical.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/), [pytest](https://pytest.org/),
[Ruff](https://docs.astral.sh/ruff/), [gitleaks](https://github.com/gitleaks/gitleaks), and the
[Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).
