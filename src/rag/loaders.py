"""Document loading: PDF, DOCX, Markdown and plain text -> list of Pages."""

from __future__ import annotations

import re
from pathlib import Path

from .types import Page

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


class UnsupportedFileType(ValueError):
    pass


def _load_pdf(path: Path) -> list[Page]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, p in enumerate(reader.pages, start=1):
        text = (p.extract_text() or "").strip()
        if text:
            pages.append(Page(path.name, i, text))
    return pages


def _load_docx(path: Path) -> list[Page]:
    from docx import Document

    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [Page(path.name, 1, text)] if text else []


_HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


def _load_text(path: Path) -> list[Page]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if path.suffix.lower() == ".md":
        # Turn "## Annual Leave" into the sentence "Annual Leave." so headings stay as context
        # but never glue themselves onto the following sentence once chunking flattens newlines.
        text = _HEADING.sub(lambda m: m.group(1).rstrip(".:") + ".", text)
    return [Page(path.name, 1, text)] if text else []


def load_document(path: str | Path) -> list[Page]:
    """Load one file. `source` is the bare file name (never a full path - safe to show users)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise UnsupportedFileType(f"Unsupported file type: {ext or '(none)'}")
    if ext == ".pdf":
        return _load_pdf(path)
    if ext == ".docx":
        return _load_docx(path)
    return _load_text(path)


def load_directory(directory: str | Path) -> list[Page]:
    pages: list[Page] = []
    for p in sorted(Path(directory).rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            pages.extend(load_document(p))
    return pages
