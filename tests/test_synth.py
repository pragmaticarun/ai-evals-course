"""evalkit.synth: tuple strategies, coverage, batching, dedup, diversity and splits."""

import json
from types import SimpleNamespace

import pytest

from evalkit import LLM
from evalkit.synth import (
    Dimension,
    Rule,
    Space,
    assign_splits,
    coverage_matrix,
    create_many,
    dedup,
    diversity_report,
    feasible_pairs,
    full_product,
    leakage_pairs,
    load_space,
    pair_coverage,
    pairwise_tuples,
    prose,
    sample_tuples,
    similarity,
    stratified_sample,
    value_counts,
)


@pytest.fixture
def small():
    dims = [
        Dimension("os", ("android", "ios"), ""),
        Dimension("codec", ("av1", "hevc", "opus"), ""),
        Dimension("kind", ("video", "audio"), ""),
    ]
    rules = [Rule({"kind": ("audio",)}, {"codec": ("av1", "hevc")}, "audio uses opus")]
    return Space(dims, rules)


def test_rules_and_full_product(small):
    assert small.product_size == 12
    full = full_product(small)
    assert len(full) == 8  # 12 minus 4 audio+video-codec tuples
    assert not small.valid({"os": "ios", "codec": "av1", "kind": "audio"})
    assert (
        small.broken_rule({"os": "ios", "codec": "av1", "kind": "audio"}).reason
        == "audio uses opus"
    )
    # partial tuples are only rejected once every field the rule mentions is present
    assert small.valid({"codec": "av1"})


def test_pairwise_covers_every_feasible_pair(small):
    tuples = pairwise_tuples(small, seed=1)
    covered, feasible = pair_coverage(tuples, small)
    assert covered == feasible == len(feasible_pairs(small))
    assert all(small.valid(t) for t in tuples)
    assert len(tuples) <= len(full_product(small))


def test_pairwise_start_only_fills_gaps(small):
    start = [{"os": "android", "codec": "opus", "kind": "audio"}]
    fill = pairwise_tuples(small, seed=1, start=start)
    assert start[0] not in fill
    assert pair_coverage(start + fill, small)[0] == len(feasible_pairs(small))


def test_sampling_is_seeded_and_valid(small):
    a, b = sample_tuples(small, 5, seed=3), sample_tuples(small, 5, seed=3)
    assert a == b and len({json.dumps(t, sort_keys=True) for t in a}) == 5
    s = stratified_sample(small, 4, by="kind", seed=3)
    assert value_counts(s, "kind") == {"video": 2, "audio": 2}


def test_coverage_matrix_marks_rules_and_gaps(small):
    rows = [{"os": "android", "codec": "av1", "kind": "video"}]
    text = coverage_matrix(rows, small, "codec", "kind")
    assert "x" in text.splitlines()[1]  # av1/audio is excluded by the rule
    assert "3 possible cells with no examples" in text


def test_load_space_rejects_unknown_values(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text(
        '[[dimension]]\nname="a"\nvalues=["x","y"]\n'
        '[[exclude]]\nwhen={a="x"}\nforbid={a="z"}\nreason="typo"\n'
    )
    with pytest.raises(ValueError, match="unknown"):
        load_space(p)


def test_course_space_numbers():
    from mediadoctor.lab04 import load_default_space

    space = load_default_space()
    assert space.product_size == 4320 and len(full_product(space)) == 1342
    pw = pairwise_tuples(space, seed=4)
    assert len(pw) == 34 and pair_coverage(pw, space) == (242, 242)
    assert pair_coverage(sample_tuples(space, 50, seed=4), space)[0] < 242


def test_similarity_ignores_pasted_logs():
    log = "11-20 14:02:11.309  8123  8194 E CCodec  : Failed to create component"
    assert prose(f"thumbnails crash\n{log}") == "thumbnails crash"
    a = f"our thumbnail grid crashes on scroll\n{log}"
    b = f"why does audio drift in this file\n{log}"
    assert similarity(a, b) == 0.0
    assert (
        similarity("Hey, why is av1.mkv choppy on the phone", "why is av1.mkv choppy on the phone")
        > 0.6
    )


def test_dedup_keeps_first_and_reports_pairs():
    items = [
        ("a", "why does the 4k av1 trailer stutter on the lumen-l3"),
        ("b", "hey, why does the 4k av1 trailer stutter on the lumen-l3"),
        ("c", "how do we request audio focus for a podcast app"),
    ]
    res = dedup(items, threshold=0.6)
    assert res.kept == ["a", "c"]
    assert res.dropped[0][:2] == ("b", "a") and res.dropped[0][2] > 0.6


def test_diversity_report_counts_llm_tells():
    rep = diversity_report(
        ["How can I fix video playback issues?", "What are the best practices for handling errors?"]
    )
    assert rep["n"] == 2 and rep["llm_tells"] >= 1


def test_grouped_splits_do_not_leak():
    items = [
        (f"q{i}", f"question number {i} about topic {i % 5} with words {i}") for i in range(40)
    ]
    items += [("dup", "question number 3 about topic 3 with words 3 again")]
    splits = assign_splits(items, salt="t", group_threshold=0.35)
    assert splits["dup"] == splits["q3"]
    assert leakage_pairs(items, splits, 0.35) == []
    assert set(splits.values()) <= {"train", "dev", "test"}


class _FakeBatchClient:
    def __init__(self):
        self.polls = 0
        self.created = []
        self.messages = SimpleNamespace(
            create=self._never,
            batches=SimpleNamespace(
                create=self._create, retrieve=self._retrieve, results=self._results
            ),
        )

    def _never(self, **_):
        raise AssertionError("batch mode must not call messages.create")

    def _create(self, requests):
        self.created = requests
        return {"id": "msgbatch_test", "processing_status": "in_progress"}

    def _retrieve(self, bid):
        self.polls += 1
        return {"id": bid, "processing_status": "ended" if self.polls > 1 else "in_progress"}

    def _results(self, bid):
        for r in self.created:
            text = r["params"]["messages"][0]["content"].upper()
            yield {
                "custom_id": r["custom_id"],
                "result": {
                    "type": "succeeded",
                    "message": {
                        "id": "m",
                        "type": "message",
                        "role": "assistant",
                        "model": "x",
                        "content": [{"type": "text", "text": text}],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                },
            }


def test_create_many_batch_records_then_replays(tmp_path, monkeypatch):
    # Recordings are keyed with the [live] model; replaying them needs the switch.
    monkeypatch.setenv("EVALS_REPLAY_LIVE_MODEL", "1")
    reqs = {
        f"r{i}": {
            "model": "m",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": f"q{i}"}],
        }
        for i in range(3)
    }
    client = _FakeBatchClient()
    sleeps = []
    rec = LLM(namespace="batch-test", mode="record", client=client, fixtures_dir=tmp_path)
    out = create_many(rec, reqs, use_batch=True, poll_seconds=7, sleep=sleeps.append)
    assert sleeps == [7] and out["r2"]["content"][0]["text"] == "Q2"
    rep = LLM(namespace="batch-test", mode="replay", fixtures_dir=tmp_path)
    again = create_many(rep, reqs)
    assert again["r1"]["content"][0]["text"] == "Q1"


def test_dedup_key_protects_different_test_cases():
    items = [
        ("a", "how do we rejoin the live edge after a long pause"),
        ("b", "how do we rejoin the live edge after a long pause, log attached"),
    ]
    assert dedup(items, threshold=0.5).kept == ["a"]
    kinds = {"a": "no-log", "b": "log"}
    assert dedup(items, threshold=0.5, key=kinds.get).kept == ["a", "b"]
