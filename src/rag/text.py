"""Tiny shared tokenizer."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have how i in is it of on or that the this to was "
    "what when where which who will with you your we our can do does".split()
)


def tokenize(text: str, drop_stopwords: bool = False) -> list[str]:
    toks = _TOKEN.findall(text.lower())
    return [t for t in toks if t not in STOPWORDS] if drop_stopwords else toks
