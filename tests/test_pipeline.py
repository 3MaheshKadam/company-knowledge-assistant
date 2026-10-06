import json
from pathlib import Path

import pytest

from rag.pipeline import MODES

QUESTIONS = [
    json.loads(line)
    for line in (Path(__file__).resolve().parent.parent / "data/eval/questions.jsonl").read_text().splitlines()
]


def test_ingest_is_idempotent(loaded_assistant):
    before = loaded_assistant.store.count()
    loaded_assistant.ingest(Path(__file__).resolve().parent.parent / "data/raw/expense_policy.txt")
    assert loaded_assistant.store.count() == before  # deterministic ids => upsert, not duplicate


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_returns_results(loaded_assistant, mode):
    assert loaded_assistant.retrieve("annual leave days", mode, 3)


def test_unknown_mode_rejected(loaded_assistant):
    with pytest.raises(ValueError):
        loaded_assistant.retrieve("x", "nope")


def test_grounded_answer_with_correct_citation(loaded_assistant):
    ans = loaded_assistant.ask("How many days of annual leave do full-time employees get?")
    assert ans.grounded and "24" in ans.answer
    assert ans.citations and all(c.source == "hr_leave_policy.md" for c in ans.citations)


def test_unanswerable_questions_abstain(loaded_assistant):
    for q in (x for x in QUESTIONS if not x["answerable"]):
        assert not loaded_assistant.ask(q["question"]).grounded, q["question"]


def test_answerable_accuracy_floor(loaded_assistant):
    qs = [q for q in QUESTIONS if q["answerable"]]
    ok = 0
    for q in qs:
        ans = loaded_assistant.ask(q["question"])
        ok += ans.grounded and all(k.lower() in ans.answer.lower() for k in q["answer_keywords"])
    assert ok / len(qs) >= 0.8


def test_delete_removes_document(settings):
    from rag.pipeline import KnowledgeAssistant

    ka = KnowledgeAssistant(settings)
    ka.ingest(Path(__file__).resolve().parent.parent / "data/raw/expense_policy.txt")
    assert ka.documents()[0]["source"] == "expense_policy.txt"
    assert ka.delete("expense_policy.txt") > 0 and ka.documents() == []
    assert ka.retrieve("meal allowance", "hybrid") == []
