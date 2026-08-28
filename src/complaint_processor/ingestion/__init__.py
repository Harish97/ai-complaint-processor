"""Document ingestion: turn files on disk into plain text plus provenance."""

from complaint_processor.ingestion.loaders import (
    LoadedDocument,
    discover_documents,
    load_document,
    supported_extensions,
)

__all__ = [
    "LoadedDocument",
    "discover_documents",
    "load_document",
    "supported_extensions",
]
