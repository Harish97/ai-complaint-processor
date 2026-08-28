"""Exception hierarchy for the complaint processing pipeline.

A single base class (`ComplaintProcessorError`) lets the batch runner catch
every *expected* failure mode in one place while still letting individual
layers raise something specific and meaningful.
"""


class ComplaintProcessorError(Exception):
    """Base class for all errors raised by this application."""


# --- Configuration -----------------------------------------------------------


class ConfigurationError(ComplaintProcessorError):
    """Raised when required configuration (e.g. an API key) is missing."""


# --- Ingestion ---------------------------------------------------------------


class IngestionError(ComplaintProcessorError):
    """Base class for document loading failures."""


class UnsupportedFormatError(IngestionError):
    """The file extension has no registered loader."""


class DocumentReadError(IngestionError):
    """The file exists but could not be parsed (corrupt, encrypted, ...)."""


class EmptyDocumentError(IngestionError):
    """The file parsed successfully but contains no usable text.

    Common with scanned/image-only PDFs, which would need OCR.
    """


# --- LLM ---------------------------------------------------------------------


class LLMError(ComplaintProcessorError):
    """Base class for LLM provider failures."""


class LLMCallError(LLMError):
    """The provider call failed after all retries were exhausted."""


class LLMResponseError(LLMError):
    """The provider responded, but the payload did not match the schema."""
