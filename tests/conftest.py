from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from rag.config import Settings
from rag.pipeline import KnowledgeAssistant

DATA = Path(__file__).resolve().parent.parent / "data" / "raw"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = Settings()
    return replace(
        base,
        chroma_dir=tmp_path / "chroma",
        upload_dir=tmp_path / "uploads",
        api_keys=("test-key-123",),
        allow_anonymous=False,
        rate_limit_per_min=1000,
        **overrides,
    )


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture(scope="session")
def loaded_assistant(tmp_path_factory) -> KnowledgeAssistant:
    """One pre-ingested assistant shared by read-only retrieval tests (ingestion is the slow part)."""
    tmp = tmp_path_factory.mktemp("kb")
    ka = KnowledgeAssistant(make_settings(tmp))
    for f in sorted(DATA.iterdir()):
        ka.ingest(f)
    return ka
