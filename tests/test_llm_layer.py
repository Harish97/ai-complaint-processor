"""Tests for the provider abstraction, the factory, and the offline provider."""

from __future__ import annotations

import pytest

from complaint_processor.config import LLMProvider, Settings
from complaint_processor.exceptions import ConfigurationError, LLMResponseError
from complaint_processor.llm import build_llm_client
from complaint_processor.llm.mock_client import MockClient
from complaint_processor.models import (
    CaseStatus,
    CaseSummary,
    ComplaintCategory,
    CustomerEmail,
    ExtractedComplaint,
)
from complaint_processor.prompts import (
    build_email_user_prompt,
    build_extraction_user_prompt,
)


# --- Factory -----------------------------------------------------------------


def test_factory_returns_mock_without_any_api_key(tmp_path):
    settings = Settings(llm_provider=LLMProvider.MOCK, output_dir=tmp_path)

    assert build_llm_client(settings).provider_name == "mock"


@pytest.mark.parametrize(
    ("provider", "env_var"),
    [(LLMProvider.OPENAI, "OPENAI_API_KEY"), (LLMProvider.GEMINI, "GEMINI_API_KEY")],
)
def test_missing_api_key_fails_fast_with_actionable_guidance(provider, env_var, tmp_path):
    """The error must arrive before the batch starts, not mid-document."""
    settings = Settings(
        llm_provider=provider, openai_api_key=None, gemini_api_key=None, output_dir=tmp_path
    )

    with pytest.raises(ConfigurationError) as exc_info:
        build_llm_client(settings)

    message = str(exc_info.value)
    assert env_var in message
    assert "--provider mock" in message  # tells the user how to proceed


# --- Offline provider behaviour ----------------------------------------------


def _extract(client: MockClient, text: str) -> ExtractedComplaint:
    return client.generate_structured(
        system_prompt="",
        user_prompt=build_extraction_user_prompt(source_file="t.txt", document_text=text),
        schema=ExtractedComplaint,
        task_name="extraction",
    )


def test_offline_provider_is_deterministic(mock_client, sample_complaint_text):
    """Determinism is what makes it usable as a test fixture."""
    first = _extract(mock_client, sample_complaint_text)
    second = _extract(mock_client, sample_complaint_text)

    assert first == second


def test_offline_provider_reads_labelled_fields(mock_client, sample_complaint_text):
    result = _extract(mock_client, sample_complaint_text)

    assert result.customer_name == "Priya Sharma"
    assert result.email == "priya.sharma@example.com"
    assert result.product_or_service == "Prime Home Broadband"
    assert result.complaint_category is ComplaintCategory.BILLING


def test_category_ignores_the_resolution_section(mock_client):
    """'A refund was issued' describes the fix, not the complaint."""
    text = (
        "Complaint Description:\nThe parcel never arrived and the courier tracking "
        "has not updated for eleven days.\n\n"
        "Resolution Provided:\nA full refund was issued to the customer.\n"
    )

    assert _extract(mock_client, text).complaint_category is ComplaintCategory.DELIVERY


@pytest.mark.parametrize(
    ("escalation_text", "expected"),
    [
        ("Not required. Resolved at first line.", False),
        ("Not requested by the customer.", False),
        ("Not yet escalated, but the delay is outside policy.", False),
        ("Handled by the service manager. Now closed.", False),
        ("Customer has requested escalation to a supervisor.", True),
        ("Escalated to the mobile engineering team.", True),
    ],
)
def test_escalation_reads_the_value_not_the_label(mock_client, escalation_text, expected):
    """Every form contains the word 'Escalation' as a heading — that is not a signal."""
    text = (
        "Complaint Description:\nThe device stopped working after two weeks.\n\n"
        f"Escalation:\n{escalation_text}\n"
    )

    assert _extract(mock_client, text).escalation_required is expected


def test_enquiry_is_not_classified_as_a_complaint(mock_client):
    text = (
        "CUSTOMER ENQUIRY\n\nEnquiry Description:\nHello, this is not a complaint. "
        "I would just like clarification before I upgrade my plan.\n"
    )

    result = _extract(mock_client, text)

    assert result.is_complaint is False
    assert result.complaint_category is ComplaintCategory.GENERAL_ENQUIRY


def test_missing_contact_details_become_null(mock_client):
    text = (
        "COMPLAINT - WEB FORM SUBMISSION\n\nComplaint Description:\n"
        "The app crashes every time I open the reports tab. I have reinstalled twice.\n"
    )

    result = _extract(mock_client, text)

    assert result.customer_name is None
    assert result.email is None
    assert result.phone_number is None
    assert "does not state" in (result.extraction_notes or "")


def test_no_resolution_means_open_status(mock_client):
    text = "Complaint Description:\nMy order has not arrived after three weeks.\n"

    assert _extract(mock_client, text).overall_case_status is CaseStatus.OPEN


def test_in_progress_beats_resolved_when_work_is_still_pending(mock_client):
    """'the refund is being processed' is not the same as 'refunded'."""
    text = (
        "Complaint Description:\nI have not received my refund.\n\n"
        "Resolution Provided:\nThe refund is currently being processed by finance.\n"
    )

    assert _extract(mock_client, text).overall_case_status is CaseStatus.IN_PROGRESS


def test_downstream_tasks_consume_the_validated_extraction(mock_client, sample_complaint_text):
    extraction = _extract(mock_client, sample_complaint_text)

    email = mock_client.generate_structured(
        system_prompt="",
        user_prompt=build_email_user_prompt(
            source_file="t.txt",
            extracted_json=extraction.model_dump_json(),
            document_text=sample_complaint_text,
        ),
        schema=CustomerEmail,
        task_name="customer_email",
    )

    assert isinstance(email, CustomerEmail)
    assert "Priya Sharma" in email.greeting


def test_offline_provider_rejects_a_schema_it_cannot_serve(mock_client):
    class Unknown(CaseSummary):
        pass

    with pytest.raises(LLMResponseError):
        mock_client.generate_structured(
            system_prompt="", user_prompt="", schema=Unknown, task_name="x"
        )


def test_usage_is_tracked(mock_client, sample_complaint_text):
    _extract(mock_client, sample_complaint_text)

    assert mock_client.usage.calls == 1
    assert mock_client.usage.total_tokens > 0
