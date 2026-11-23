from types import SimpleNamespace

import pytest

from evalkit import LLM, FixtureMissingError, Mode, text_of

REQ = {"model": "m", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
RESP = {"content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn"}


class FakeClient:
    def __init__(self):
        self.seen = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        self.seen.append(request)
        return RESP


def test_default_mode_is_replay():
    assert LLM(fixtures_dir=None).mode is Mode.REPLAY


def test_replay_never_calls_client(tmp_path):
    fake = FakeClient()
    llm = LLM("ns", mode="replay", fixtures_dir=tmp_path, client=fake)
    with pytest.raises(FixtureMissingError):
        llm.create(**REQ)
    assert fake.seen == [] and llm.calls == 0


def test_record_then_replay(tmp_path, monkeypatch):
    # Recordings are keyed with the [live] model; replaying them needs the switch.
    monkeypatch.setenv("EVALS_REPLAY_LIVE_MODEL", "1")
    fake = FakeClient()
    rec = LLM("ns", mode="record", fixtures_dir=tmp_path, client=fake)
    assert text_of(rec.create(**REQ)) == "hello"
    assert rec.calls == 1
    replay = LLM("ns", mode="replay", fixtures_dir=tmp_path)
    assert text_of(replay.create(**REQ)) == "hello"
    assert '"source":"live"' in (tmp_path / "ns.jsonl").read_text()


def test_live_does_not_write(tmp_path):
    llm = LLM("ns", mode="live", fixtures_dir=tmp_path, client=FakeClient())
    llm.create(**REQ)
    assert not (tmp_path / "ns.jsonl").exists()


def test_live_without_key_fails_clearly(tmp_path):
    llm = LLM("ns", mode="live", fixtures_dir=tmp_path)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm.create(**REQ)


def test_pydantic_like_responses_are_converted(tmp_path):
    class Obj:
        def model_dump(self, **_):
            return RESP

    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: Obj()))
    llm = LLM("ns", mode="record", fixtures_dir=tmp_path, client=client)
    assert llm.create(**REQ) == RESP


def test_text_of_ignores_non_text_blocks():
    resp = {
        "content": [
            {"type": "thinking", "thinking": "x"},
            {"type": "text", "text": "a"},
            {"type": "tool_use", "name": "t"},
            {"type": "text", "text": "b"},
        ]
    }
    assert text_of(resp) == "ab"


def test_record_stores_latency_and_replay_returns_it(tmp_path, monkeypatch):
    # Recordings are keyed with the [live] model; replaying them needs the switch.
    monkeypatch.setenv("EVALS_REPLAY_LIVE_MODEL", "1")
    t = {"now": 0.0}

    def clock():
        return t["now"]

    class SlowClient(FakeClient):
        def _create(self, **request):
            t["now"] += 1.25
            return RESP

    rec = LLM(
        "ns",
        mode="record",
        fixtures_dir=tmp_path,
        client=SlowClient(),
        clock=clock,
        source="synthetic-authored",
    )
    rec.create(**REQ)
    assert rec.last_latency_ms == 1250.0 and rec.last_replayed is False
    line = (tmp_path / "ns.jsonl").read_text()
    assert '"latency_ms":1250.0' in line and '"source":"synthetic-authored"' in line
    rep = LLM("ns", mode="replay", fixtures_dir=tmp_path)
    rep.create(**REQ)
    assert rep.last_latency_ms == 1250.0 and rep.last_replayed is True


def test_trials_record_and_replay_separately(tmp_path, monkeypatch):
    """Module 6: the same request recorded as trials 0 and 1 replays two different answers."""
    # Recordings are keyed with the [live] model; replaying them needs the switch.
    monkeypatch.setenv("EVALS_REPLAY_LIVE_MODEL", "1")
    answers = iter(["first", "second"])

    class Varying:
        messages = SimpleNamespace(
            create=lambda **r: {
                "content": [{"type": "text", "text": next(answers)}],
                "stop_reason": "end_turn",
            }
        )

    for trial in (0, 1):
        LLM("ns", mode="record", fixtures_dir=tmp_path, client=Varying(), trial=trial).create(**REQ)
    got = [
        text_of(LLM("ns", mode="replay", fixtures_dir=tmp_path, trial=t).create(**REQ))
        for t in (0, 1)
    ]
    assert got == ["first", "second"]
    with pytest.raises(FixtureMissingError):
        LLM("ns", mode="replay", fixtures_dir=tmp_path, trial=2).create(**REQ)


def test_incomplete_stops_are_named():
    from evalkit.llm import incomplete_stop

    for stop in ("max_tokens", "refusal", "pause_turn"):
        assert incomplete_stop(stop)
    for stop in ("end_turn", "stop_sequence", "tool_use", None):
        assert incomplete_stop(stop) is None


def test_agent_marks_a_truncated_answer_as_an_error():
    from evalkit import LLM, Tracer
    from mediadoctor.toolagent import run_agent

    class Client:
        class messages:  # noqa: N801
            @staticmethod
            def create(**_):
                return {
                    "content": [{"type": "text", "text": "Likely cause: the decoder"}],
                    "stop_reason": "max_tokens",
                    "usage": {"input_tokens": 10, "output_tokens": 1024},
                }

    tracer = Tracer()
    run_agent("why?", LLM(mode="live", client=Client()), tracer, case_id="t1")
    root = next(s for s in tracer.span_dicts() if s["parent_span_id"] is None)
    assert root["status"]["code"] == "ERROR" and "max_tokens" in root["status"]["message"]
