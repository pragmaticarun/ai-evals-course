# Start here: study plan

The course takes about **87 hours**: 12 modules, each with a lesson, an offline lab, exercises with collapsed
solutions, and a quiz (module 12 has a self-assessment instead). At **about 7 hours a week** that is **13 weeks**,
with four hours of slack. Every lab runs offline from recorded responses, so you need no API key until you choose
to re-record live.

!!! info "Synthetic data, real method"
    The model responses, traces, and production traffic in this course are **synthetic-authored**: written by the
    scripts in `scripts/` so that every lab is reproducible and the failures are known. Every fixture is labelled
    `"source": "synthetic-authored"`. The code (agent, tools, checks, judges' prompts, statistics, CI gate) is real,
    and the numbers show how the methods behave, not how Claude models behave on your system. Each lab says what
    is synthetic and how to re-record live.

## Before week 1

- Read [Setup](setup.md) and run `uv sync && uv run pytest -q` (about 15 minutes on Ubuntu).
- Skim the [course map](index.md#course-map) and the [eval loop cheat sheet](cheatsheets/eval-loop.md).
- Keep a notebook file (`runs/notes.md`; `runs/` is ignored by git) for the one-line answers each week asks for.

## The 13-week plan

| Week | Hours | Work | You finish the week with |
|---|---|---|---|
| 1 | 7 | Setup; [module 1](modules/01-why-evals/index.md) (all, 4 h); [module 2](modules/02-agent-with-tracing/index.md) lesson (3 h) | Three code checks and a per-case diff of two prompts |
| 2 | 7 | Module 2 lab, exercises, quiz (5 h); [module 3](modules/03-error-analysis/index.md) lesson (2 h) | Traces with tokens, cost, and latency on every call; trace checks |
| 3 | 7 | Module 3 lab: label 100 traces, axial coding, ranking (5 h); [module 4](modules/04-synthetic-data/index.md) lesson (2 h) | Failure taxonomy v1 and a Pareto chart |
| 4 | 7 | Module 4 lab, exercises, quiz (4 h); [module 5](modules/05-evaluators-and-judges/index.md) lesson (3 h) | A dimensions sheet and a deduplicated, split synthetic dataset |
| 5 | 7 | Module 5 lab, exercises, quiz (6 h); review weeks 1 to 5 (1 h) | Three judges with TPR and TNR on a test split; a corrected pass rate |
| 6 | 7 | [Module 6](modules/06-trustworthy-metrics/index.md), all (6 h); slack (1 h) | Intervals on every metric; a paired comparison; a sample-size estimate |
| 7 | 7 | [Module 7](modules/07-architectures/index.md) lesson and lab: retrieval, RAG, multi-turn (7 h) | Retrieval metrics, RAG attribution, a simulated-user test |
| 8 | 7 | Module 7 multi-agent and vision, exercises, quiz (3 h); [module 8](modules/08-ci-cd/index.md) lesson and lab (4 h) | A transition-failure matrix; an eval gate on a pull request |
| 9 | 7 | Module 8 exercises and quiz (2 h); [module 9](modules/09-monitoring-and-annotation/index.md) lesson and lab (5 h) | A golden set with a manifest; production monitors and alarms |
| 10 | 7 | Module 9 annotation app, exercises, quiz (3 h); [module 10](modules/10-red-teaming/index.md) lesson and lab (4 h) | An annotation queue with agreement; an attack suite |
| 11 | 7 | Module 10 exercises and quiz (3 h); [module 11](modules/11-improving-with-evidence/index.md) lesson and first half of the lab (4 h) | Attack success and false-positive rates; a pre-registration |
| 12 | 7 | Module 11 lab, exercises, quiz (4 h); [module 12](modules/12-capstone/index.md) lesson and lab sections 1 to 6 (3 h) | An experiment log, a decision memo, a chosen capstone slice |
| 13 | 7 | Module 12: report, review, publish, present (5 h); slack (2 h) | Your [capstone eval report](capstone/index.md), published on your copy of the site |

The weekly hours are estimates for an experienced engineer who reads the lesson once, does the lab carefully, and
tries every exercise before opening its solution. Modules 3 (reading 100 traces) and 7 (four architectures) run
long for most people; the slack weeks are there for them.

## If you have less time

The **core path** (about 48 hours, 7 weeks) keeps the loop intact: modules 1, 2, 3, 5, 6, 8, and 12. You lose
synthetic data (use module 4's committed dataset as is), the architecture-specific evaluations, production
monitoring, red-teaming, and the cost and latency experiments; the capstone report will have shorter sections for
those, built from the committed artifacts.

## If you want to go further

- Re-record any lab live with your own key and compare (most labs have an optional section for it; module 12's
  [Make it your own](modules/12-capstone/extensions.md), option A). Estimate the cost before re-recording (module 2 shows tokens and cost per call; module 11 has `mediadoctor-lab11 cost`).
- Build the alternative project, **CrashTriage** (Android tombstone and ANR triage), alongside MediaDoctor from
  module 3 on, and use it as your capstone slice.
- Read the sources on the [Credits](credits.md) page, starting with Hamel Husain and Shreya Shankar's
  [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) and their
  [course](https://maven.com/parlance-labs/evals).

## Reference pages

- [All cheat sheets](cheatsheets/index.md), one per module, with the one-line rules on a single page.
- [All templates](eval-templates/index.md): taxonomy, dimensions, judge prompt, experiment log, decision memo, and
  eval report.
- [Glossary](glossary.md): every term, with the module that introduces it.
- [Versions checked](versions.md): the tool and model versions the course was last verified against.
