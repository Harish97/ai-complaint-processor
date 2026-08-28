"""Task 1: document text -> validated `ExtractedComplaint`."""

from __future__ import annotations

from complaint_processor.llm.base import LLMClient
from complaint_processor.logging_setup import get_logger
from complaint_processor.models import ExtractedComplaint
from complaint_processor.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    build_extraction_user_prompt,
)

logger = get_logger(__name__)

TASK_NAME = "extraction"


def extract_complaint(
    *, client: LLMClient, source_file: str, document_text: str
) -> ExtractedComplaint:
    """Extract the structured case record from one document.

    The returned object has already passed Pydantic validation *and* the
    normalising validators on `ExtractedComplaint` — placeholder strings are now
    `None`, and malformed emails and phone numbers have been dropped. The raw
    provider payload is never returned to the caller.
    """
    user_prompt = build_extraction_user_prompt(
        source_file=source_file, document_text=document_text
    )

    result = client.generate_structured(
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=ExtractedComplaint,
        task_name=TASK_NAME,
    )

    logger.info(
        "Extracted %s | category=%s status=%s escalate=%s",
        source_file,
        result.complaint_category.value,
        result.overall_case_status.value,
        result.escalation_required,
    )
    return result
