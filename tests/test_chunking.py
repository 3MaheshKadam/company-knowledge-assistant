import pytest

from rag.chunking import chunk_page, chunk_pages
from rag.types import Page


def test_overlap_and_coverage():
    page = Page("a.txt", 1, " ".join(f"w{i}" for i in range(100)))
    chunks = chunk_page(page, size=40, overlap=10)
    assert [c.index for c in chunks] == [0, 1, 2]
    assert chunks[0].text.split()[-10:] == chunks[1].text.split()[:10]  # overlap preserved
    assert "w99" in chunks[-1].text  # nothing lost at the tail


def test_short_page_single_chunk():
    assert len(chunk_page(Page("a.txt", 1, "just a few words"), size=50, overlap=5)) == 1


def test_ids_are_deterministic_and_unique():
    page = Page("a.txt", 1, " ".join(f"w{i}" for i in range(200)))
    a, b = chunk_page(page, 50, 10), chunk_page(page, 50, 10)
    assert [c.id for c in a] == [c.id for c in b]
    assert len({c.id for c in a}) == len(a)


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_params(size, overlap):
    with pytest.raises(ValueError):
        chunk_page(Page("a", 1, "x y z"), size, overlap)


def test_empty_pages_yield_no_chunks():
    assert chunk_pages([Page("a", 1, "   ")]) == []
