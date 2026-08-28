"""Task 2: validated extraction -> professional customer response email."""

from __future__ import annotations

from complaint_processor.llm.base import LLMClient
from complaint_processor.logging_setup import get_logger
from complaint_processor.models import CustomerEmail, ExtractedComplaint
from complaint_processor.prompts import EMAIL_SYSTEM_PROMPT, build_email_user_prompt

logger = get_logger(__name__)

TASK_NAME = "customer_email"


def generate_customer_email(
    *,
    client: LLMClient,
    source_file: str,
    extraction: ExtractedComplaint,
    document_text: str,
) -> CustomerEmail:
    """Generate the customer-facing reply for one case."""
    user_prompt = build_email_user_prompt(
        source_file=source_file,
        extracted_json=extraction.model_dump_json(indent=2),
        document_text=document_text,
    )

    email = client.generate_structured(
        system_prompt=EMAIL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=CustomerEmail,
        task_name=TASK_NAME,
    )

    logger.info("Drafted customer email for %s | subject=%r", source_file, email.subject)
    return email
