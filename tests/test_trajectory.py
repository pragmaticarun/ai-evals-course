"""evalkit.trajectory: tool-set metrics, order, efficiency, first failure, transition matrix."""

from evalkit.trajectory import (
    START,
    first_failure,
    format_matrix,
    in_order,
    step_efficiency,
    tool_precision,
    tool_recall,
    transition_matrix,
)


def test_tool_sets():
    assert tool_recall(["ffprobe", "codec_caps"], ["ffprobe"]) == 0.5
    assert tool_recall([], ["ffprobe"]) == 1.0
    assert tool_precision(["ffprobe"], ["ffprobe", "search_kb"]) == 0.5
    assert tool_precision(["ffprobe"], []) == 1.0


def test_in_order_is_a_subsequence():
    assert in_order(["ffprobe", "codec_caps"], ["search_kb", "ffprobe", "x", "codec_caps"])
    assert not in_order(["ffprobe", "codec_caps"], ["codec_caps", "ffprobe"])
    assert in_order([], ["anything"])


def test_step_efficiency():
    assert step_efficiency(4, 4) == 1.0
    assert step_efficiency(4, 5) == 0.8
    assert step_efficiency(4, 2) == 1.0  # fewer steps than "minimal" is capped, not rewarded
    assert step_efficiency(4, 0) == 0.0


def test_first_failure_and_matrix():
    states = ["plan", "handoff", "codec_caps", "answer"]
    oks = [True, True, False, False]
    assert first_failure(states, lambda i, s: oks[i]) == ("handoff", "codec_caps")
    assert first_failure(states, lambda i, s: i > 0) == (START, "plan")
    assert first_failure(states, lambda i, s: True) is None
    rows, cols, counts = transition_matrix(
        [("handoff", "codec_caps"), ("handoff", "codec_caps"), (START, "plan"), None]
    )
    assert rows == [START, "handoff"]
    assert cols == ["codec_caps", "plan"]
    assert counts[("handoff", "codec_caps")] == 2
    text = format_matrix(rows, cols, counts)
    assert "handoff" in text and "2" in text.splitlines()[2]
