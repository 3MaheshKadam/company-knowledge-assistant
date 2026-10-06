from rag.bm25 import BM25Index
from rag.hybrid import rrf_fuse
from rag.types import Chunk, Hit


def mk(i, text):
    return Chunk(f"c{i}", text, "s.txt", 1, i)


def test_bm25_ranks_rare_term_match_first():
    idx = BM25Index()
    idx.build([mk(0, "the cat sat on the mat"), mk(1, "quarterly revenue grew strongly"), mk(2, "cat food prices")])
    hits = idx.search("revenue growth quarterly", 3)
    assert hits[0].chunk.id == "c1"


def test_bm25_no_match_returns_empty():
    idx = BM25Index()
    idx.build([mk(0, "alpha beta")])
    assert idx.search("zzz", 3) == []


def test_bm25_empty_index():
    assert BM25Index().search("anything", 3) == []


def test_rrf_math_and_order():
    a = [Hit(mk(1, "x"), 0.9), Hit(mk(2, "y"), 0.8)]
    b = [Hit(mk(2, "y"), 5.0), Hit(mk(3, "z"), 4.0)]
    fused = rrf_fuse([a, b], k=60)
    assert fused[0].chunk.id == "c2"  # appears in both lists
    assert abs(fused[0].score - (1 / 62 + 1 / 61)) < 1e-12
    assert {h.chunk.id for h in fused} == {"c1", "c2", "c3"}


def test_rrf_top_n():
    a = [Hit(mk(i, "t"), 1.0) for i in range(5)]
    assert len(rrf_fuse([a], top_n=2)) == 2
