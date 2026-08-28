"""Prompt templates, kept separate from task logic so they can be tuned alone."""

from complaint_processor.prompts.case_summary import (
    SUMMARY_SYSTEM_PROMPT,
    build_summary_user_prompt,
)
from complaint_processor.prompts.extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    build_extraction_user_prompt,
)
from complaint_processor.prompts.response_email import (
    EMAIL_SYSTEM_PROMPT,
    build_email_user_prompt,
)

__all__ = [
    "EXTRACTION_SYSTEM_PROMPT",
    "EMAIL_SYSTEM_PROMPT",
    "SUMMARY_SYSTEM_PROMPT",
    "build_extraction_user_prompt",
    "build_email_user_prompt",
    "build_summary_user_prompt",
]
