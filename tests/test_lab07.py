"""Module 7 lab: retrieval numbers, RAG attribution, chat sessions, multi-agent trajectories, and
vision judges all replay and match the lesson."""

import dataclasses
import json

import pytest

from evalkit import LLM, FixtureMissingError
from mediadoctor import chat, lab07, multiagent, rag, vision


def test_kb_v2_and_relevance_labels():
    secs = rag.sections()
    assert len(secs) == 57
    qs = rag.queries()
    assert len(qs) == 48
    assert {q.topic for q in qs} == set(lab07.TOPICS)
    assert all(q.answering and q.answering <= q.relevant <= set(secs) for q in qs)


def test_chunkers_cover_every_word_once():
    for chunker in rag.CHUNKERS:
        words = sum(len(c.text.split()) for c in rag.chunks(chunker))
        assert words >= sum(len(w) for w in rag.corpus().values()) * 0.8
    assert all(c.section in rag.sections() for c in rag.chunks("fixed"))


def test_stemming_and_bm25_ranks_the_obvious_section_first():
    assert rag.stem("decoders") == "decoder" and rag.stem("crashes") == "crash"
    top = rag.search("BehindLiveWindowException after resuming a live stream", "section", "bm25", 1)
    assert top[0].doc == "behind-live-window"


def test_retrieval_table_matches_the_lesson():
    rows = {r["config"]: r for r in lab07.retrieval_rows()}
    assert rows["fixed+keyword"]["recall"][0] == pytest.approx(0.64, abs=0.005)
    assert rows["section+bm25"]["recall"][0] == pytest.approx(0.81, abs=0.005)
    assert rows["fixed+keyword"]["codec"] == pytest.approx(0.51, abs=0.005)
    assert rows["section+bm25"]["codec"] == pytest.approx(0.62, abs=0.005)
    assert rows["section+bm25"]["mrr"] > rows["fixed+keyword"]["mrr"]
    (d, lo, hi), n = lab07.recall_diff(("fixed", "keyword"), ("section", "bm25"))
    assert n == 48 and lo > 0
    (d, lo, hi), n = lab07.recall_diff(("fixed", "keyword"), ("section", "bm25"), topic="codec")
    assert n == 14 and lo < 0 < hi  # the codec gain is not established


def test_rag_runs_replay_and_every_failure_is_a_retrieval_failure():
    runs = lab07.rag_runs()
    assert len(runs) == 96
    assert set(runs) == set(lab07.rag_labels())
    base, imp = lab07.attribution("baseline"), lab07.attribution("improved")
    assert base["retrieval failure"] == 12 and imp["retrieval failure"] == 8
    assert base["pass"] == 36 and imp["pass"] == 40
    # with an answering passage in context the generator never failed: the next fix is retrieval
    assert base["generation failure"] == imp["generation failure"] == 0
    assert base["pass despite miss"] == imp["pass despite miss"] == 0
    for r in runs.values():  # an answer cites only what the code check says it cites
        assert r.answer.startswith("Answer:")


def test_citation_check_catches_ids_outside_the_context():
    runs = lab07.rag_runs()
    checks = {i: lab07.citation_checks(r) for i, r in runs.items()}
    assert all(c["valid"] for c in checks.values())  # every recorded citation is in the context
    assert sum(not c["cites"] for c in checks.values()) == 12  # abstentions cite nothing
    for system in ("baseline", "improved"):  # ...but valid is not the same as relevant
        assert sum(c["supports"] for i, c in checks.items() if i.startswith(system)) == 40
    assert not checks["baseline:r04"]["supports"]
    r = runs["improved:r04"]
    forged = dataclasses.replace(r, answer=r.answer + " [kb:widevine-levels#1]")
    assert not lab07.citation_checks(forged)["valid"]  # an id outside the context is caught


def test_rag_judges_are_validated():
    f = lab07.rag_judge_confusion("faithfulness")
    assert f.n == 96 and f.tnr < f.tpr  # misses some unfaithful answers
    r = lab07.rag_judge_confusion("answer-relevance")
    assert r.agreement > 0.85


def test_chat_sessions_replay():
    ss = lab07.sessions()
    assert len(ss) == 32
    for s in ss.values():
        assert len(s.user_turns) <= chat.MAX_USER_TURNS
        assert s.turns[0] == ("user", chat.scenarios()[s.scenario].opening)
    rows = lab07.chat_rows()
    # the code check (cause named in the final answer) disagrees with the labels on 4 sessions:
    # three hedged v1 answers name a cause without committing to it, one v2 answer phrases it
    # in words the regex does not know
    wrong = {r["id"] for r in rows if r["resolved"] != r["resolved_label"]}
    assert wrong == {"c05-v1", "c06-v1", "c13-v1", "c16-v2"}
    v1 = sum(r["resolved"] for r in rows if r["prompt"] == "v1")
    v2 = sum(r["resolved"] for r in rows if r["prompt"] == "v2")
    assert (v1, v2) == (16, 15)
    v1 = sum(r["resolved_label"] for r in rows if r["prompt"] == "v1")
    v2 = sum(r["resolved_label"] for r in rows if r["prompt"] == "v2")
    assert (v1, v2) == (13, 16)


def test_turn_checks_find_retention_and_needless_questions():
    rows = {r["id"]: r for r in lab07.chat_rows()}
    labels = lab07.session_labels()
    for sid, r in rows.items():
        assert r["re_ask"] == (labels[sid]["re_ask"] == "yes"), sid
        assert r["needless"] == (labels[sid]["needless_question"] == "yes"), sid


def test_simulator_checks_agree_with_labels_and_catch_a_volunteered_fact():
    flagged = {r["id"] for r in lab07.chat_rows() if r["sim_problems"]}
    labelled = {s for s, lab in lab07.session_labels().items() if lab["simulator_issue"]}
    assert flagged == labelled == set()  # the recorded simulated users kept to their rules
    s = lab07.sessions()["c07-v2"]  # the agent asked for the log only; answer with every fact
    sc = chat.scenarios()[s.scenario]
    leaky = chat.Session(s.id, s.scenario, s.prompt,
                         [s.turns[0], s.turns[1], ("user", " ".join(sc.facts.values()))])  # fmt: skip
    assert chat.simulator_problems(sc, leaky) == ["turn 3: volunteered 'code' without being asked"]


def test_gave_up_judge():
    c = lab07.gave_up_confusion()
    assert (c.tp, c.fn, c.tn, c.fp) == (29, 0, 0, 3)  # passes every session: misses all 3 give-ups


def test_trajectories_of_module_5():
    rows = lab07.trajectory_rows()
    assert len(rows) == 108
    missing = [r for r in rows if r["recall"] < 1]
    # skipping an expected tool did not decide the outcome: all 4 such runs still passed
    assert len(missing) == 4 and all(r["passed"] for r in missing)
    assert sum(not r["passed"] for r in rows) == 2


def test_multiagent_matrix():
    runs = lab07.team_runs()
    assert len(runs) == 47
    fails = [lab07.failure_of(r) for r in runs.values()]
    assert sum(f is not None for f in fails) == 2
    rows, cols, counts = lab07.transition_matrix(fails)
    assert dict(counts) == {("evidence", "answer"): 2}  # both failures are synthesis
    assert sum(not lab07.states(r)[0][1] for r in runs.values()) == 11  # wrong routes, all passed
    no_evidence = set()
    for cid, r in runs.items():
        ref = lab07.agent_refs()[cid]
        if ref["verdict"] == "pass" and lab07.states(r)[-2] != ("evidence", True):
            no_evidence.add(cid)
    assert no_evidence == {"m4q052", "m4q163", "m4q192"}  # passed without the expected evidence


def test_specialists_only_get_their_tools():
    req = multiagent._request(
        "s", [{"role": "user", "content": "x"}], multiagent.SPECIALISTS["media"]
    )
    assert {t["name"] for t in req["tools"]} == {"ffprobe", "search_kb"}
    assert multiagent.parse_plan('{"route": ["media", "nope"], "brief": "b"}') == (["media"], "b")
    assert multiagent.parse_plan("not json") == ([], "")


def test_vision_requests_are_compact_in_fixtures():
    imgs = vision.images()
    assert len(imgs) == 22
    path = lab07.repo_root() / "fixtures" / "recorded" / f"{vision.NAMESPACE}.jsonl"
    text = path.read_text(encoding="utf-8")
    assert "data_sha256" in text and "iVBORw0KGgo" not in text  # no PNG base64 in the fixture
    rec = json.loads(text.splitlines()[0])
    assert rec["source"] == "subagent-authored"


def test_vision_numbers():
    rows = lab07.frame_rows()
    blk = [r for r in rows if r["judge"] == "frame-blocking" and r["present"]]
    assert sum(r["flagged"] for r in blk if r["severity"] == "severe") == 3
    assert sum(r["flagged"] for r in blk if r["severity"] == "mild") == 3
    alarms = [
        r["image"]
        for r in rows
        if r["judge"] == "frame-blocking" and not r["present"] and r["flagged"]
    ]
    assert len(alarms) == 4 and all(a.startswith("banding_") for a in alarms)
    answers = lab07.spectrogram_answers()
    right = sum(
        vision.defect_of(a) == imgs.artifact
        for n, a in answers.items()
        for imgs in [vision.images()[n]]
    )
    assert right == 6


def test_changed_image_is_a_fixture_miss(tmp_path, monkeypatch):
    img = tmp_path / "frames"
    img.mkdir()
    src = vision.frames_dir() / "clean_bars.png"
    (img / "clean_bars.png").write_bytes(src.read_bytes() + b"\0")
    monkeypatch.setattr(vision, "frames_dir", lambda: img)
    llm = LLM(namespace=vision.NAMESPACE)
    with pytest.raises(FixtureMissingError):
        llm.create(**vision.judge_request(lab07.spec("frame-blocking"), "clean_bars.png"))


def test_report_and_cli(capsys):
    text = lab07.report()
    for part in (
        "Retrieval",
        "RAG generation",
        "Multi-turn chat",
        "Planner and specialists",
        "Images",
    ):
        assert f"## {part}" in text
    for cmd in (
        ["retrieval"],
        ["misses", "--topic", "codec"],
        ["session", "c05-v2"],
        ["run", "m4q010"],
    ):
        assert lab07.main(cmd) == 0
    assert "codec_caps" in capsys.readouterr().out
