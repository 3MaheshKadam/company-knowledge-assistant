from rag.citations import build_answer, verify
from rag.generator import NO_ANSWER
from rag.types import Chunk, Hit

HITS = [
    Hit(Chunk("a", "Full-time employees receive 24 days of paid annual leave per calendar year.", "hr.md", 1, 0), 1.0),
    Hit(Chunk("b", "The company observes 11 public holidays each year.", "hr.md", 1, 1), 0.9),
]


def test_supported_sentence_is_kept_with_citation():
    ans = build_answer("leave?", "Employees receive 24 days of paid annual leave [1].", HITS)
    assert ans.grounded and ans.faithfulness == 1.0
    assert [c.source for c in ans.citations] == ["hr.md"]


def test_wrong_number_is_dropped():
    ans = build_answer("leave?", "Employees receive 30 days of paid annual leave [1].", HITS)
    assert not ans.grounded and ans.answer == NO_ANSWER and ans.dropped_claims


def test_missing_marker_is_dropped():
    ans = build_answer("leave?", "Employees receive 24 days of paid annual leave.", HITS)
    assert not ans.grounded


def test_invalid_marker_is_dropped():
    assert not build_answer("q", "Employees receive 24 days of leave [9].", HITS).grounded


def test_mixed_answer_keeps_supported_and_reports_partial_faithfulness():
    raw = "Employees receive 24 days of paid annual leave [1]. Remote work is unlimited [2]."
    ans = build_answer("q", raw, HITS)
    assert ans.grounded and ans.faithfulness == 0.5 and len(ans.dropped_claims) == 1
    assert "Remote" not in ans.answer


def test_marker_must_point_at_supporting_chunk():
    v = verify("Employees receive 24 days of paid annual leave [2].", HITS)
    assert not v[0].supported  # real fact, but cited to the wrong chunk


def test_no_answer_passthrough():
    assert not build_answer("q", NO_ANSWER, HITS).grounded
    assert not build_answer("q", "anything [1].", []).grounded
