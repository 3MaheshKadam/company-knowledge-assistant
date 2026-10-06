"""Shared data types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Page:
    """One page/section of a source document."""

    source: str
    page: int
    text: str


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str
    page: int
    index: int


@dataclass(frozen=True)
class Hit:
    """A retrieval result with its score and the stage that produced it."""

    chunk: Chunk
    score: float
    stage: str = ""


@dataclass
class Citation:
    marker: int  # the [n] number shown in the answer
    chunk_id: str
    source: str
    page: int
    snippet: str


@dataclass
class Answer:
    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    grounded: bool = True
    faithfulness: float = 1.0
    dropped_claims: list[str] = field(default_factory=list)
