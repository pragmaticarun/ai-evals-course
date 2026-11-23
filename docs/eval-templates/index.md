# Templates

Six templates, in the order the course uses them. Each is a Markdown page you can copy into `runs/` (or your own
repository) and fill in; the module that introduces it has a worked example.

| Template | First used | Fill it in when you... | Worked example |
|---|---|---|---|
| [Failure taxonomy sheet](failure-taxonomy.md) | Module 3 | label traces and group failures into modes | [Module 3](../modules/03-error-analysis/index.md) |
| [Dimensions sheet](dimensions-sheet.md) | Module 4 | plan synthetic test queries | [Module 4](../modules/04-synthetic-data/index.md) |
| [Judge prompt](judge-prompt.md) | Module 5 | write a binary LLM judge for one failure mode | [Module 5](../modules/05-evaluators-and-judges/index.md) |
| [Experiment log](experiment-log.md) | Module 11 | pre-register an experiment, then record what happened | [Module 11](../modules/11-improving-with-evidence/index.md) |
| [Decision memo](decision-memo.md) | Module 11 | ask one person to decide, on one page | [Module 11](../modules/11-improving-with-evidence/index.md) |
| [Eval report](eval-report.md) | Module 12 | write up a whole evaluation for stakeholders | [Reference report](../capstone/index.md) |

How they fit together: the **taxonomy** says what fails; the **dimensions sheet** finds more of it; the **judge
prompt** measures it; the **experiment log** records each attempt to fix it; the **decision memo** asks for one
decision; and the **eval report** holds all of it, with the evidence a reviewer needs.

Tools that fill them in for MediaDoctor: `mediadoctor-lab03 rank --taxonomy` (taxonomy CSV),
`mediadoctor-lab11 log` and `memo` (experiment log and decision memo), and `mediadoctor-capstone report`
(eval report). Each generated draft has the right numbers and generic prose; edit the prose.
