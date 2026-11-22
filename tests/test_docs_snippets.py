"""Docs integrity: nav targets exist, and every `# exercise-solution` snippet runs as written."""

import re
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

FENCE = re.compile(r"^(?P<indent>[ \t]*)```python\n(?P<body>.*?)^(?P=indent)```", re.M | re.S)


def _nav_targets() -> list[str]:
    text = (ROOT / "mkdocs.yml").read_text()
    nav = text.split("\nnav:", 1)[1]
    return re.findall(r"([\w\-/]+\.md)", nav)


def test_every_nav_entry_exists():
    targets = _nav_targets()
    assert len(targets) >= 25
    missing = [t for t in targets if not (DOCS / t).is_file()]
    assert not missing, missing


def _solution_snippets():
    for md in sorted(DOCS.rglob("*.md")):
        for m in FENCE.finditer(md.read_text()):
            body = textwrap.dedent(m.group("body"))
            if body.lstrip().startswith("# exercise-solution"):
                yield pytest.param(body, id=f"{md.relative_to(DOCS)}:{m.start()}")


SNIPPETS = list(_solution_snippets())


def test_there_are_solution_snippets():
    assert len(SNIPPETS) >= 2


@pytest.mark.parametrize("code", SNIPPETS)
def test_solution_snippet_runs(code):
    exec(compile(code, "<snippet>", "exec"), {"__name__": "__snippet__"})


@pytest.mark.parametrize(
    "module",
    [
        "01-why-evals",
        "02-agent-with-tracing",
        "03-error-analysis",
        "04-synthetic-data",
        "05-evaluators-and-judges",
        "06-trustworthy-metrics",
        "07-architectures",
        "08-ci-cd",
        "09-monitoring-and-annotation",
    ],
)
def test_solutions_are_collapsed(module):
    text = (DOCS / "modules" / module / "exercises.md").read_text()
    assert text.count('??? success "Solution"') == 5
    assert "!!! success" not in text


@pytest.mark.parametrize(
    ("module", "n"),
    [
        ("02-agent-with-tracing", 8),
        ("03-error-analysis", 10),
        ("04-synthetic-data", 8),
        ("05-evaluators-and-judges", 10),
        ("06-trustworthy-metrics", 10),
        ("07-architectures", 10),
        ("08-ci-cd", 8),
        ("09-monitoring-and-annotation", 8),
    ],
)
def test_quiz_answers_are_collapsed(module, n):
    text = (DOCS / "modules" / module / "quiz.md").read_text()
    assert text.count('??? question "Answer"') == n
