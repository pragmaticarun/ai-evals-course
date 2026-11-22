# AI Evals, Hands-On

An original, self-paced course on evaluating LLM agents. You build one agent, **MediaDoctor**, which answers Android
and multimedia debugging questions, and you work through the whole eval loop with it: find where it breaks, measure
those failures with evaluators you can trust, and improve it with evidence.

- **12 modules**, about 87 hours in total (an estimate), designed for about 7 hours a week.
- **Hands-on**: every module has a lab that runs offline from recorded model responses, exercises with
  collapsed solutions, and a quiz.
- **Live runs on Claude** through the Anthropic Python SDK when you want them; CI never needs a key.

## Course map

| # | Module | Hours | Status |
|---|---|---|---|
| 1 | [Why evals](modules/01-why-evals/index.md) | 4 | Available |
| 2 | [A measurable agent with tracing](modules/02-agent-with-tracing/index.md) | 8 | Available |
| 3 | [Error analysis](modules/03-error-analysis/index.md) | 7 | Available |
| 4 | [Synthetic data](modules/04-synthetic-data/index.md) | 6 | Available |
| 5 | [Evaluators and judge validation](modules/05-evaluators-and-judges/index.md) | 9 | Available |
| 6 | [Trustworthy metrics and statistics](modules/06-trustworthy-metrics/index.md) | 6 | Planned |
| 7 | [Architectures: RAG, multi-turn, multi-agent, multimodal](modules/07-architectures/index.md) | 10 | Planned |
| 8 | [CI/CD for agents](modules/08-ci-cd/index.md) | 6 | Planned |
| 9 | [Production monitoring and annotation app](modules/09-monitoring-and-annotation/index.md) | 8 | Planned |
| 10 | [Red-teaming and safety](modules/10-red-teaming/index.md) | 7 | Planned |
| 11 | [Improving with evidence](modules/11-improving-with-evidence/index.md) | 8 | Planned |
| 12 | [Capstone eval report](modules/12-capstone/index.md) | 8 | Planned |

## Who it is for

Experienced engineers who are comfortable with Python, git, and the command line. No ML background is assumed.
Examples lean on Android media and multimedia, but each one is explained as it comes up.

## Standing on shoulders

The structure of this course is inspired by Hamel Husain and Shreya Shankar's work on AI evals, including their
Maven course and public writing. All text, code, and data here are original. See [Credits](credits.md).

Start with [Setup](setup.md), then [Module 1](modules/01-why-evals/index.md),
[Module 2](modules/02-agent-with-tracing/index.md), [Module 3](modules/03-error-analysis/index.md),
[Module 4](modules/04-synthetic-data/index.md), and [Module 5](modules/05-evaluators-and-judges/index.md).
