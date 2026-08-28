"""Task 3: validated extraction -> internal management case summary."""

from __future__ import annotations

from complaint_processor.llm.base import LLMClient
from complaint_processor.logging_setup import get_logger
from complaint_processor.models import CaseSummary, ExtractedComplaint
from complaint_processor.prompts import SUMMARY_SYSTEM_PROMPT, build_summary_user_prompt

logger = get_logger(__name__)

TASK_NAME = "case_summary"


def generate_case_summary(
    *,
    client: LLMClient,
    source_file: str,
    extraction: ExtractedComplaint,
    document_text: str,
) -> CaseSummary:
    """Generate the internal case note for one case."""
    user_prompt = build_summary_user_prompt(
        source_file=source_file,
        extracted_json=extraction.model_dump_json(indent=2),
        document_text=document_text,
    )

    summary = client.generate_structured(
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=CaseSummary,
        task_name=TASK_NAME,
    )

    logger.info("Wrote case summary for %s", source_file)
    return summary
