"""File loaders.

Each format gets a small `DocumentLoader` subclass and registers the extensions
it handles. Adding a new format (e.g. `.rtf`) means writing one class and adding
it to `_LOADERS` — no other module changes.

Supported out of the box: `.txt`, `.md`, `.pdf`, `.docx`.
"""

from __future__ import annotations

import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from complaint_processor.exceptions import (
    DocumentReadError,
    EmptyDocumentError,
    UnsupportedFormatError,
)
from complaint_processor.logging_setup import get_logger

logger = get_logger(__name__)

# Files starting with these are editor/OS artefacts, never real input.
_IGNORED_PREFIXES = (".", "~$")


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """Plain text extracted from a file, plus the provenance we need later."""

    path: Path
    text: str
    file_type: str
    file_size_bytes: int

    @property
    def char_count(self) -> int:
        return len(self.text)


def _normalise(text: str) -> str:
    """Tidy extracted text without changing its meaning.

    PDF and DOCX extraction routinely produce non-breaking spaces, smart quotes
    and ragged blank lines. Normalising here keeps prompts clean and token counts
    predictable, and means downstream code only ever sees one flavour of text.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip() for line in text.split("\n")]

    # Collapse runs of 3+ blank lines down to a single blank line.
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            blank_run = 0
            cleaned.append(line)
        else:
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
    return "\n".join(cleaned).strip()


class DocumentLoader(ABC):
    """Base class for format-specific text extraction."""

    extensions: tuple[str, ...] = ()

    @abstractmethod
    def extract_text(self, path: Path) -> str:
        """Return the raw text of `path`, or raise `DocumentReadError`."""

    def load(self, path: Path) -> LoadedDocument:
        try:
            raw = self.extract_text(path)
        except DocumentReadError:
            raise
        except Exception as exc:  # noqa: BLE001 - deliberately broad at the boundary
            raise DocumentReadError(f"Failed to read {path.name}: {exc}") from exc

        text = _normalise(raw)
        if not text:
            raise EmptyDocumentError(
                f"{path.name} contains no extractable text "
                "(a scanned or image-only file would need OCR)"
            )

        return LoadedDocument(
            path=path,
            text=text,
            file_type=path.suffix.lower().lstrip("."),
            file_size_bytes=path.stat().st_size,
        )


class TextLoader(DocumentLoader):
    """Plain text and Markdown."""

    extensions = (".txt", ".md")

    def extract_text(self, path: Path) -> str:
        # Real-world exports are not always UTF-8; fall back rather than crash.
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                logger.debug("%s is not %s, trying next encoding", path.name, encoding)
        raise DocumentReadError(f"Could not decode {path.name} with any known encoding")


class PdfLoader(DocumentLoader):
    """PDF via pypdf. Page-by-page so one bad page cannot lose the whole file."""

    extensions = (".pdf",)

    def extract_text(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - environment problem
            raise DocumentReadError(
                "pypdf is not installed; run `pip install -r requirements.txt`"
            ) from exc

        reader = PdfReader(str(path))

        if reader.is_encrypted:
            # An empty password unlocks many "protected" business PDFs.
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise DocumentReadError(f"{path.name} is password-protected") from exc

        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping page %d of %s: %s", index, path.name, exc)
        return "\n\n".join(pages)


class DocxLoader(DocumentLoader):
    """Word documents via python-docx, including text held in tables."""

    extensions = (".docx",)

    def extract_text(self, path: Path) -> str:
        try:
            import docx
        except ImportError as exc:  # pragma: no cover - environment problem
            raise DocumentReadError(
                "python-docx is not installed; run `pip install -r requirements.txt`"
            ) from exc

        document = docx.Document(str(path))
        parts = [paragraph.text for paragraph in document.paragraphs]

        # Complaint forms often put the useful fields inside a table.
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))

        return "\n".join(parts)


_LOADERS: tuple[DocumentLoader, ...] = (TextLoader(), PdfLoader(), DocxLoader())

_EXTENSION_MAP: dict[str, DocumentLoader] = {
    extension: loader for loader in _LOADERS for extension in loader.extensions
}


def supported_extensions() -> tuple[str, ...]:
    """Every extension the application can ingest, sorted for stable display."""
    return tuple(sorted(_EXTENSION_MAP))


def load_document(path: Path) -> LoadedDocument:
    """Load one file, dispatching on its extension."""
    loader = _EXTENSION_MAP.get(path.suffix.lower())
    if loader is None:
        raise UnsupportedFormatError(
            f"No loader for '{path.suffix or path.name}'. "
            f"Supported: {', '.join(supported_extensions())}"
        )
    if not path.is_file():
        raise DocumentReadError(f"{path} is not a readable file")

    document = loader.load(path)
    logger.debug(
        "Loaded %s (%s, %d bytes, %d chars)",
        document.path.name,
        document.file_type,
        document.file_size_bytes,
        document.char_count,
    )
    return document


def discover_documents(input_dir: Path) -> tuple[list[Path], list[Path]]:
    """Scan `input_dir` for input files.

    Returns `(eligible, skipped)` — files with a registered loader, and files
    that were present but cannot be processed. Reporting skipped files rather
    than silently ignoring them is part of handling batches honestly.
    """
    if not input_dir.exists():
        raise DocumentReadError(f"Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise DocumentReadError(f"Input path is not a directory: {input_dir}")

    eligible: list[Path] = []
    skipped: list[Path] = []

    for path in sorted(input_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith(_IGNORED_PREFIXES):
            continue
        if path.suffix.lower() in _EXTENSION_MAP:
            eligible.append(path)
        else:
            skipped.append(path)

    logger.info(
        "Discovered %d processable file(s) in %s (%d skipped)",
        len(eligible),
        input_dir,
        len(skipped),
    )
    return eligible, skipped
