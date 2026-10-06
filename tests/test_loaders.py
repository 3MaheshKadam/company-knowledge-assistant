import pytest
from docx import Document

from rag.loaders import UnsupportedFileType, load_directory, load_document


def minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


def test_text_and_markdown(tmp_path):
    (tmp_path / "a.md").write_text("# Title\nbody text", encoding="utf-8")
    pages = load_document(tmp_path / "a.md")
    assert pages[0].source == "a.md" and "body text" in pages[0].text
    assert pages[0].text.startswith("Title.")  # heading became its own sentence, no '#' left


def test_docx(tmp_path):
    d = Document()
    d.add_paragraph("Leave policy is generous")
    d.save(tmp_path / "p.docx")
    assert "generous" in load_document(tmp_path / "p.docx")[0].text


def test_pdf(tmp_path):
    (tmp_path / "p.pdf").write_bytes(minimal_pdf("Policy states 42 days"))
    pages = load_document(tmp_path / "p.pdf")
    assert pages and "42" in pages[0].text and pages[0].page == 1


def test_unsupported(tmp_path):
    (tmp_path / "x.exe").write_bytes(b"MZ")
    with pytest.raises(UnsupportedFileType):
        load_document(tmp_path / "x.exe")


def test_directory_skips_unsupported(tmp_path):
    (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
    (tmp_path / "b.bin").write_bytes(b"\x00")
    assert [p.source for p in load_directory(tmp_path)] == ["a.txt"]
