import json

import pytest

from evalkit.gate import Status
from evalkit.golden import HoldoutAccessError, HoldoutGuard
from mediadoctor import lab06, lab08, toolagent


@pytest.fixture(scope="module")
def v1():
    return lab08.run_suite("v1", lab08.TIERS)


@pytest.fixture(scope="module")
def v2():
    return lab08.run_suite("v2", lab08.TIERS)


def test_splits():
    s = lab08.golden_splits()
    assert (len(s["gate"]), len(s["judges"]), len(s["holdout"])) == (119, 30, 28)


def test_replay_matches_modules_5_and_6(v1, v2):
    for prompt, run in (("v1", v1), ("v2", v2)):
        items = lab06.items(prompt, 1)
        assert all(items[c].answer == a for c, a in run.answers.items())
    assert not v1.judge_misses and not v2.judge_misses


def test_release_v1_matches_the_committed_baseline(v1):
    assert lab08.release_prompt() == "v1"
    assert lab08.baseline_problems(v1, lab08.load_baseline().run) == []


def test_v2_passes_with_a_citations_warning(v1, v2):
    code = lab08.compare(v1, v2, "code")
    assert not code.blocked
    status = {m.metric: m.status for m in code.metrics}
    assert status == {
        "format": Status.PASS,
        "citations": Status.WARN,
        "investigated": Status.PASS,
        "all-code-checks": Status.PASS,
    }
    flips = {m.metric: (m.result.a_only, m.result.b_only) for m in code.metrics}
    assert flips == {
        "format": (0, 0),
        "citations": (3, 0),  # too few flips to block, too many to rule out a 0.05 drop
        "investigated": (3, 9),
        "all-code-checks": (5, 9),
    }
    judges = lab08.compare(v1, v2, "judges")
    assert not judges.blocked
    assert {m.metric: (m.result.n, m.result.a_only, m.result.b_only) for m in judges.metrics} == {
        "false-premise": (30, 0, 0),
        "tool-grounding": (30, 0, 0),
        "next-step": (30, 0, 0),
    }


def test_report_markdown(v1, v2):
    gates = {t: lab08.compare(v1, v2, t) for t in lab08.TIERS}
    md = lab08.report_markdown(v1, v2, gates, "base ref")
    assert md.startswith("## Eval gate: ⚠️ passed with warnings")
    assert "| citations | 119 | 1.000 | 0.975 |" in md
    assert "cannot rule out a drop larger than 0.05" in md
    assert "| citations | m4q003 | newly failing | Likely cause:" in md  # flips show head answers
    assert "### Cost and time" in md


def test_prompt_text_change_is_a_replay_miss(monkeypatch):
    ids = lab08.ids_in(["dev"])
    assert lab08.preflight("v1", ids) == []
    edited = toolagent.AGENT_PROMPTS["v1"].replace("Android", "Android and ChromeOS")
    monkeypatch.setitem(toolagent.AGENT_PROMPTS, "v1", edited)
    assert lab08.preflight("v1", ids) == ids
    with pytest.raises(lab08.ReplayMissError) as exc:
        lab08.run_suite("v1", ("code",))
    assert len(exc.value.missing) == 119


def test_fingerprint_tracks_prompt_and_model(monkeypatch):
    fp = lab08.fingerprint("v1")
    assert fp != lab08.fingerprint("v2")
    real = toolagent.load_models

    def other_model():
        roles = dict(real())
        roles["agent"] = type(roles["agent"])(**{**vars(roles["agent"]), "model": "claude-x"})
        return roles

    monkeypatch.setattr(toolagent, "load_models", other_model)
    assert lab08.fingerprint("v1") != fp


def test_gate_tiers_do_not_touch_the_holdout():
    g = HoldoutGuard(frozenset(lab08.holdout_ids()))
    lab08.run_suite("v1", ("code",), holdout_guard=g)
    assert g.looks == 0
    with pytest.raises(HoldoutAccessError):
        g.check(lab08.holdout_ids(), "tuning")
    rel = lab08.run_suite("v1", ("code",), release=True, holdout_guard=g)
    assert g.looks == 1 and len(rel.outcomes["code"]["format"]) == 28


def test_manifest_and_hygiene_are_clean():
    assert lab08.manifest_problems() == []
    h = lab08.hygiene()
    assert h.problems == []
    assert h.contamination == [] and not h.unreviewed_contamination
    assert h.closest[0][2] < 0.35


def test_cli_gate_exit_codes(tmp_path, capsys):
    summary = tmp_path / "summary.md"
    assert lab08.main(["gate", "--summary", str(summary)]) == 0
    assert "✅ passed" in summary.read_text()
    out = tmp_path / "v2.md"
    assert (
        lab08.main(
            ["gate", "--prompt", "v2", "--out", str(out), "--json", str(tmp_path / "h.json")]
        )
        == 0  # a warning does not fail the job; only a block (exit 1) does
    )
    assert "⚠️ passed with warnings" in out.read_text()
    saved = json.loads((tmp_path / "h.json").read_text())
    assert saved["config"]["prompt"] == "v2" and len(saved["tiers"]["code"]["format"]) == 119


def test_cli_run_and_diff(tmp_path):
    for p in ("v1", "v2"):
        assert (
            lab08.main(
                ["run", "--prompt", p, "--tier", "all", "--out", str(tmp_path / f"{p}.json")]
            )
            == 0
        )
    assert (
        lab08.main(
            [
                "diff",
                str(tmp_path / "v1.json"),
                str(tmp_path / "v2.json"),
                "--out",
                str(tmp_path / "d.md"),
            ]
        )
        == 0
    )
    md = (tmp_path / "d.md").read_text()
    assert md.startswith("## v1 → v2: ⚠️ passed with warnings") and "LLM judges" in md


def test_baseline_from_a_ref_without_one_falls_back():
    b = lab08.load_baseline("0000000000000000000000000000000000000000")
    assert "has no usable baseline" in b.source
    assert b.run.prompt == "v1"


def test_baseline_on_another_major_golden_version_is_not_compared(monkeypatch):
    doc = json.loads(lab08.baseline_path().read_text())
    doc["golden"]["version"] = "1.0.1"
    monkeypatch.setattr(lab08, "git_show", lambda ref, path: json.dumps(doc))
    b = lab08.load_baseline("1111111111111111111111111111111111111111")
    assert "in this checkout" in b.source and "not comparable" in b.source
    doc["golden"]["version"] = lab08.GOLDEN_VERSION.split(".")[0] + ".9.9"  # same major: compared
    b = lab08.load_baseline("1111111111111111111111111111111111111111")
    assert b.source.endswith("at 111111111111")


def test_usage_estimates_missing_latency(v1):
    assert v1.usage["judges"].latency_s > 60  # module 5's judge records carry no latency
    assert lab08.estimated_latency_ms(1000, 50) == pytest.approx(1140.0)
