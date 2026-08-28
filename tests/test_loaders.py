"""Tests for document ingestion."""

from __future__ import annotations

from pathlib import Path

import pytest

from complaint_processor.exceptions import (
    EmptyDocumentError,
    UnsupportedFormatError,
)
from complaint_processor.ingestion import (
    discover_documents,
    load_document,
    supported_extensions,
)


def test_supported_extensions_cover_the_brief():
    """The brief requires at least two formats; we support four."""
    extensions = supported_extensions()
    assert {".txt", ".pdf", ".docx"} <= set(extensions)
    assert len(extensions) >= 2


def test_loads_plain_text(tmp_path: Path):
    path = tmp_path / "case.txt"
    path.write_text("Customer Name: Alice\nIssue: broken widget", encoding="utf-8")

    document = load_document(path)

    assert "Alice" in document.text
    assert document.file_type == "txt"
    assert document.char_count == len(document.text)
    assert document.file_size_bytes > 0


def test_loads_markdown(tmp_path: Path):
    path = tmp_path / "case.md"
    path.write_text("# Case\n\n- **Customer Name:** Bob\n", encoding="utf-8")

    assert "Bob" in load_document(path).text


def test_loads_docx_including_table_text(tmp_path: Path):
    docx = pytest.importorskip("docx")

    path = tmp_path / "case.docx"
    document = docx.Document()
    document.add_heading("CASE FORM", level=1)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Customer Name"
    table.rows[0].cells[1].text = "Carol"
    document.add_paragraph("The device stopped working.")
    document.save(str(path))

    text = load_document(path).text
    # Text held in tables must be picked up, not just body paragraphs.
    assert "Carol" in text
    assert "stopped working" in text


def test_loads_pdf(tmp_path: Path):
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    path = tmp_path / "case.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 720, "Customer Name: Dave")
    pdf.drawString(72, 700, "The parcel never arrived.")
    pdf.save()

    text = load_document(path).text
    assert "Dave" in text
    assert "parcel" in text


def test_empty_file_raises(tmp_path: Path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    with pytest.raises(EmptyDocumentError):
        load_document(path)


def test_unsupported_extension_raises(tmp_path: Path):
    path = tmp_path / "sheet.xlsx"
    path.write_bytes(b"not a spreadsheet")

    with pytest.raises(UnsupportedFormatError):
        load_document(path)


def test_non_utf8_text_still_loads(tmp_path: Path):
    """Real exports are not always UTF-8; the loader must not crash."""
    path = tmp_path / "latin.txt"
    path.write_bytes("Customer: Renée Café".encode("latin-1"))

    assert "Customer" in load_document(path).text


def test_discover_separates_eligible_from_skipped(tmp_path: Path):
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / "b.md").write_text("two", encoding="utf-8")
    (tmp_path / "c.xlsx").write_bytes(b"three")
    (tmp_path / ".DS_Store").write_bytes(b"junk")
    (tmp_path / "~$draft.docx").write_bytes(b"lock file")

    eligible, skipped = discover_documents(tmp_path)

    assert [p.name for p in eligible] == ["a.txt", "b.md"]
    assert [p.name for p in skipped] == ["c.xlsx"]  # OS/editor artefacts ignored entirely


def test_normalisation_collapses_blank_line_runs(tmp_path: Path):
    path = tmp_path / "ragged.txt"
    path.write_text("Line one\n\n\n\n\nLine two   \n", encoding="utf-8")

    assert load_document(path).text == "Line one\n\nLine two"
