"""Tests for the Pydantic schemas and their normalising validators.

These validators are what turn a raw model response into trustworthy data, so
they carry most of the correctness weight in the project.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from complaint_processor.models import (
    CaseStatus,
    CaseSummary,
    ComplaintCategory,
    CustomerEmail,
    ExtractedComplaint,
    Priority,
    Sentiment,
)


def _extraction(**overrides) -> ExtractedComplaint:
    """Build a valid extraction, overriding only the field under test."""
    base = {
        "customer_name": "Priya Sharma",
        "email": "priya@example.com",
        "phone_number": "+91 98765 43210",
        "product_or_service": "Broadband",
        "complaint_category": ComplaintCategory.BILLING,
        "issue_description": "Billed twice in February.",
        "resolution_provided": "Refund approved.",
        "is_complaint": True,
        "escalation_required": False,
        "supporting_document_available": True,
        "overall_case_status": CaseStatus.RESOLVED,
        "priority": Priority.LOW,
        "customer_sentiment": Sentiment.NEUTRAL,
        "extraction_notes": None,
    }
    return ExtractedComplaint(**{**base, **overrides})


# --- Placeholder normalisation ----------------------------------------------


@pytest.mark.parametrize("placeholder", ["N/A", "n/a", "unknown", "Not provided", "none", "  ", "-"])
def test_placeholder_strings_become_none(placeholder: str):
    """LLMs love emitting 'N/A'; the report must show an empty cell, not the word."""
    assert _extraction(customer_name=placeholder).customer_name is None


def test_whitespace_is_collapsed():
    assert _extraction(customer_name="  Priya   Sharma \n").customer_name == "Priya Sharma"


# --- Email validation --------------------------------------------------------


@pytest.mark.parametrize("bad", ["not-an-email", "missing@tld", "@example.com", "a b@c.com"])
def test_malformed_email_is_dropped(bad: str):
    """A hallucinated address is worse than no address, so it is discarded."""
    assert _extraction(email=bad).email is None


def test_valid_email_is_normalised_to_lowercase():
    assert _extraction(email="  <Priya.Sharma@Example.COM> ").email == "priya.sharma@example.com"


# --- Phone validation --------------------------------------------------------


@pytest.mark.parametrize("bad", ["12", "abc", "555"])
def test_implausible_phone_is_dropped(bad: str):
    assert _extraction(phone_number=bad).phone_number is None


@pytest.mark.parametrize("good", ["+91 98765 43210", "080-4455-9012", "(555) 123-4567"])
def test_plausible_phone_is_kept_verbatim(good: str):
    """Formatting is preserved — reformatting a number risks corrupting it."""
    assert _extraction(phone_number=good).phone_number == good


# --- Required fields ---------------------------------------------------------


def test_blank_issue_description_is_rejected():
    with pytest.raises(ValidationError):
        _extraction(issue_description="   ")


def test_invalid_enum_value_is_rejected():
    with pytest.raises(ValidationError):
        _extraction(complaint_category="Wibble")


def test_display_name_falls_back_when_name_missing():
    assert _extraction(customer_name=None).display_name == "Customer"
    assert _extraction(customer_name="Priya").display_name == "Priya"


# --- Rendering ---------------------------------------------------------------


def test_customer_email_renders_all_parts():
    email = CustomerEmail(
        subject="Your billing case",
        greeting="Dear Priya,",
        body_paragraphs=["We are sorry.", "It is fixed."],
        closing="Kind regards,",
        sender_name="Support Team",
    )

    rendered = email.render()

    assert rendered.startswith("Subject: Your billing case")
    for fragment in ("Dear Priya,", "We are sorry.", "It is fixed.", "Support Team"):
        assert fragment in rendered


def test_email_with_no_usable_paragraphs_is_rejected():
    with pytest.raises(ValidationError):
        CustomerEmail(
            subject="s",
            greeting="g",
            body_paragraphs=["", "   "],
            closing="c",
            sender_name="n",
        )


def test_case_summary_renders_the_five_required_sections():
    summary = CaseSummary(
        case_overview="Billing case.",
        key_issue="Duplicate charge.",
        action_taken="Refund issued.",
        current_status="Resolved.",
        recommended_next_action="Close the case.",
    )

    rendered = summary.render()

    for heading in (
        "Case Overview",
        "Key Issue",
        "Action Taken",
        "Current Status",
        "Recommended Next Action",
    ):
        assert heading in rendered


def test_schema_has_no_defaults_for_strict_structured_output():
    """OpenAI strict mode requires every property to be required.

    A default sneaking onto an LLM-facing schema breaks the OpenAI provider at
    runtime, so it is asserted here rather than discovered mid-batch.
    """
    for schema in (ExtractedComplaint, CustomerEmail, CaseSummary):
        for name, field in schema.model_fields.items():
            assert field.is_required(), f"{schema.__name__}.{name} must not have a default"
