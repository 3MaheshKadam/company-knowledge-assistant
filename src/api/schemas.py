"""Request/response models (strict validation = first line of defence)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: Literal["dense", "bm25", "hybrid", "hybrid_rerank"] = "hybrid_rerank"


class CitationOut(BaseModel):
    marker: int
    source: str
    page: int
    chunk_id: str
    snippet: str


class AskResponse(BaseModel):
    question: str
    answer: str
    grounded: bool
    faithfulness: float
    citations: list[CitationOut]
    dropped_claims: list[str]
    cached: bool = False


class JobAccepted(BaseModel):
    job_id: str
    status: str
    status_url: str


class PageOut(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int
    next_offset: int | None
