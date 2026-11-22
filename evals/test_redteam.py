"""Fast tier (module 10): red-team cases as regression tests for the release guardrails.

Replays the synthetic-authored attack suite and benign traffic under the release guard (config/
redteam/gate.toml) and fails when a known attack works again, a new attack works, a canary reaches
the user, a budget is exceeded, or the suite is worse than the baseline committed on the base branch.
"""

import os

import pytest

from evalkit.gate import GateRule, Status, describe, evaluate_gate
from mediadoctor import guarded as G
from mediadoctor import lab10

CFG = lab10.config()
GUARD, APPROVER = CFG["release_guard"], CFG["approver"]


@pytest.fixture(scope="module")
def head():
    return lab10.outcomes(GUARD, APPROVER)


@pytest.mark.parametrize("cid", CFG["must_block"])
def test_known_attack_stays_blocked(cid):
    r = lab10.run_case(lab10.case(cid), GUARD, APPROVER)
    assert not lab10.success(r), f"{cid} works again: {r.result.answer[:200]}"


def test_no_unlisted_attack_works(head):
    worked = {cid for cid, ok in head["attack_blocked"].items() if not ok}
    assert worked <= set(CFG["accepted_risks"]), sorted(worked - set(CFG["accepted_risks"]))


def test_accepted_risks_are_still_real(head):
    # When an accepted risk gets fixed, move it to must_block so it stays fixed.
    fixed = [cid for cid in CFG["accepted_risks"] if head["attack_blocked"][cid]]
    assert not fixed, f"now blocked, move to must_block: {fixed}"


def test_no_canary_or_secret_reaches_the_user():
    leaked = [
        r.case["id"]
        for r in lab10.runs(GUARD, APPROVER)
        if G.PROMPT_CANARY in r.result.answer or G.secrets_in(r.result.answer)
    ]
    assert not leaked


def test_within_budgets():
    assert lab10.asr(GUARD, APPROVER).p <= CFG["max_attack_success_rate"]
    assert lab10.fpr(GUARD, APPROVER).p <= CFG["max_benign_false_positive_rate"]


def test_no_regression_against_baseline(head):
    base = lab10.load_baseline(os.environ.get("EVAL_GATE_BASE_REF") or None)
    res = evaluate_gate(
        {m: (base["outcomes"][m], head[m]) for m in ("attack_blocked", "benign_untouched")},
        GateRule(alpha=CFG["alpha"], margin=CFG["margin"]),
    )
    fails = [m for m in res.metrics if m.status is Status.FAIL]
    assert not fails, describe(fails)
