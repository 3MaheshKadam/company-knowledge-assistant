"""Citation verification (the grounding step).

For every sentence in the generated answer we check:
  1. it carries at least one [n] marker pointing at a real retrieved chunk;
  2. the cited chunk actually supports the sentence: enough of the sentence's content words appear
     in the chunk, and every number in the sentence appears in the chunk (numbers are where
     hallucinations hurt most - "20 days" vs "25 days").
Unsupported sentences are dropped and reported. Faithfulness = supported / total claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .generator import NO_ANSWER
from .text import tokenize
from .types import Answer, Citation, Hit

_MARKER = re.compile(r"\[(\d+)\]")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?!\[\d+\])")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class Verdict:
    sentence: str
    markers: list[int]
    support: float
    supported: bool


def _support(sentence: str, chunk_text: str) -> float:
    toks = set(tokenize(_MARKER.sub("", sentence), drop_stopwords=True))
    if not toks:
        return 0.0
    ctoks = set(tokenize(chunk_text))
    nums = set(_NUM.findall(_MARKER.sub("", sentence)))
    if nums and not all(n in chunk_text for n in nums):
        return 0.0
    return len(toks & ctoks) / len(toks)


def verify(raw_answer: str, hits: list[Hit], min_support: float = 0.5) -> list[Verdict]:
    verdicts = []
    for sent in (s.strip() for s in _SPLIT.split(raw_answer.strip()) if s.strip()):
        markers = [int(m) for m in _MARKER.findall(sent)]
        valid = [m for m in markers if 1 <= m <= len(hits)]
        best = max((_support(sent, hits[m - 1].chunk.text) for m in valid), default=0.0)
        verdicts.append(Verdict(sent, markers, best, bool(valid) and best >= min_support))
    return verdicts


def build_answer(question: str, raw_answer: str, hits: list[Hit], min_support: float = 0.5) -> Answer:
    if raw_answer.strip() == NO_ANSWER or not hits:
        return Answer(question, NO_ANSWER, [], grounded=False, faithfulness=1.0)
    verdicts = verify(raw_answer, hits, min_support)
    kept = [v for v in verdicts if v.supported]
    dropped = [v.sentence for v in verdicts if not v.supported]
    if not kept:
        return Answer(question, NO_ANSWER, [], grounded=False, faithfulness=0.0, dropped_claims=dropped)
    used = sorted({m for v in kept for m in v.markers if 1 <= m <= len(hits)})
    citations = [
        Citation(m, hits[m - 1].chunk.id, hits[m - 1].chunk.source, hits[m - 1].chunk.page,
                 hits[m - 1].chunk.text[:200])
        for m in used
    ]
    return Answer(
        question=question,
        answer=" ".join(v.sentence for v in kept),
        citations=citations,
        grounded=True,
        faithfulness=len(kept) / len(verdicts),
        dropped_claims=dropped,
    )
