"""Pydantic schemas for the pipeline.

Two families of models live here:

1. **LLM-facing schemas** (`ExtractedComplaint`, `CustomerEmail`, `CaseSummary`)
   are handed to the provider as a response schema. They deliberately declare
   *no field defaults* — OpenAI's strict structured-output mode requires every
   property to be required, so "optional" values are modelled as `T | None`.

2. **Internal schemas** (`DocumentMeta`, `CaseRecord`) are ordinary application
   models and may use defaults freely.

The validators on `ExtractedComplaint` are what turn a raw model response into
trustworthy data: placeholder strings are normalised to `None`, emails and phone
numbers are format-checked, and free text is stripped. The application never
persists the raw LLM payload as-is.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Strings LLMs commonly emit instead of a null value.
_NULL_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "null",
    "nil",
    "unknown",
    "not provided",
    "not available",
    "not specified",
    "not mentioned",
    "not applicable",
    "no email provided",
    "no phone provided",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE_ALLOWED_RE = re.compile(r"[^\d+]")


def _blank_to_none(value: str | None) -> str | None:
    """Collapse whitespace and map placeholder text to a real `None`."""
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if cleaned.lower() in _NULL_PLACEHOLDERS:
        return None
    return cleaned or None


# --- Controlled vocabularies -------------------------------------------------


class ComplaintCategory(str, Enum):
    """Closed set of categories, so the report can be aggregated reliably."""

    BILLING = "Billing"
    DELIVERY = "Delivery"
    PRODUCT_DEFECT = "Product Defect"
    SERVICE_QUALITY = "Service Quality"
    TECHNICAL_ISSUE = "Technical Issue"
    ACCOUNT_ACCESS = "Account Access"
    REFUND = "Refund"
    WARRANTY = "Warranty"
    GENERAL_ENQUIRY = "General Enquiry"
    OTHER = "Other"


class CaseStatus(str, Enum):
    """Lifecycle state of the case as described by the source document."""

    RESOLVED = "Resolved"
    IN_PROGRESS = "In Progress"
    PENDING_CUSTOMER = "Pending Customer"
    ESCALATED = "Escalated"
    OPEN = "Open"
    CLOSED = "Closed"


class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Sentiment(str, Enum):
    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"
    VERY_NEGATIVE = "Very Negative"


class ProcessingStatus(str, Enum):
    """Outcome of the workflow for one document."""

    SUCCESS = "SUCCESS"  # all three AI tasks completed
    PARTIAL = "PARTIAL"  # extraction worked, a downstream task did not
    FAILED = "FAILED"  # nothing usable was produced


# --- Task 1: structured extraction (LLM-facing) ------------------------------


class ExtractedComplaint(BaseModel):
    """Structured record extracted from a single complaint document.

    Every field the assessment brief lists is present. Fields that may legitimately
    be absent from a source document are typed `... | None` rather than given a
    default, which keeps the schema compatible with strict structured outputs.
    """

    model_config = ConfigDict(use_enum_values=False, validate_assignment=True)

    customer_name: str | None = Field(
        description="Full name of the customer. Null if the document does not state it."
    )
    email: str | None = Field(
        description="Customer email address exactly as written. Null if absent."
    )
    phone_number: str | None = Field(
        description="Customer phone number exactly as written. Null if absent."
    )
    product_or_service: str | None = Field(
        description="The product or service the case concerns. Null if not stated."
    )
    complaint_category: ComplaintCategory = Field(
        description="The single category that best describes the issue."
    )
    issue_description: str = Field(
        description=(
            "Concise factual restatement of the customer's problem, 1-3 sentences, "
            "using only information present in the document."
        )
    )
    resolution_provided: str | None = Field(
        description=(
            "The resolution or action the company has already taken. "
            "Null if the document records no resolution yet."
        )
    )
    is_complaint: bool = Field(
        description="True if this document is a complaint; False for a query or feedback."
    )
    escalation_required: bool = Field(
        description=(
            "True if the document indicates escalation is needed or already happened, "
            "or the issue is unresolved and severe."
        )
    )
    supporting_document_available: bool = Field(
        description=(
            "True if the document references attachments or supporting evidence "
            "such as invoices, receipts, photos, screenshots or logs."
        )
    )
    overall_case_status: CaseStatus = Field(
        description="Current lifecycle status of the case per the document."
    )
    priority: Priority = Field(
        description="Operational priority implied by severity and customer impact."
    )
    customer_sentiment: Sentiment = Field(
        description="Tone expressed by the customer in the document."
    )
    extraction_notes: str | None = Field(
        description=(
            "Short note on anything ambiguous or missing in the source document. "
            "Null if the document was unambiguous."
        )
    )

    # --- Post-validation: this is what makes the output trustworthy ---

    @field_validator(
        "customer_name",
        "product_or_service",
        "resolution_provided",
        "extraction_notes",
        mode="after",
    )
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("issue_description", mode="after")
    @classmethod
    def _clean_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("issue_description must not be empty")
        return cleaned

    @field_validator("email", mode="after")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        cleaned = _blank_to_none(value)
        if cleaned is None:
            return None
        cleaned = cleaned.strip("<>,;").lower()
        # An invalid address is dropped rather than propagated: sending mail to a
        # hallucinated address is worse than recording that we have none.
        return cleaned if _EMAIL_RE.match(cleaned) else None

    @field_validator("phone_number", mode="after")
    @classmethod
    def _validate_phone(cls, value: str | None) -> str | None:
        cleaned = _blank_to_none(value)
        if cleaned is None:
            return None
        digits = _PHONE_ALLOWED_RE.sub("", cleaned)
        # Require a plausible length; anything shorter is noise, not a number.
        return cleaned if 7 <= len(digits.lstrip("+")) <= 15 else None

    @property
    def display_name(self) -> str:
        """Safe salutation target for the generated email."""
        return self.customer_name or "Customer"


# --- Task 2: customer response email (LLM-facing) ----------------------------


class CustomerEmail(BaseModel):
    """A professional response email, generated as structured parts.

    Generating the parts separately (rather than one blob of text) means the
    application controls the final layout and can validate each piece.
    """

    subject: str = Field(description="Concise, specific email subject line.")
    greeting: str = Field(description="Salutation line, e.g. 'Dear Ms Sharma,'.")
    body_paragraphs: list[str] = Field(
        description=(
            "Two to four paragraphs: acknowledge the issue, restate it accurately, "
            "state the resolution or current status, and set the next expectation. "
            "Use only facts from the source document."
        )
    )
    closing: str = Field(description="Closing line, e.g. 'Kind regards,'.")
    sender_name: str = Field(description="Sign-off identity, e.g. 'Customer Support Team'.")

    @field_validator("subject", "greeting", "closing", "sender_name", mode="after")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("email field must not be empty")
        return cleaned

    @field_validator("body_paragraphs", mode="after")
    @classmethod
    def _clean_paragraphs(cls, value: list[str]) -> list[str]:
        paragraphs = [" ".join(p.split()) for p in value]
        paragraphs = [p for p in paragraphs if p]
        if not paragraphs:
            raise ValueError("email body must contain at least one paragraph")
        return paragraphs

    def render(self) -> str:
        """Assemble the parts into a sendable plain-text email."""
        lines = [f"Subject: {self.subject}", "", self.greeting, ""]
        for paragraph in self.body_paragraphs:
            lines.extend([paragraph, ""])
        lines.extend([self.closing, self.sender_name, ""])
        return "\n".join(lines)


# --- Task 3: internal case summary (LLM-facing) ------------------------------


class CaseSummary(BaseModel):
    """Internal management summary — the five sections the brief specifies."""

    case_overview: str = Field(description="One or two sentences framing the case.")
    key_issue: str = Field(description="The single core problem, stated plainly.")
    action_taken: str = Field(
        description="What has already been done. State 'No action recorded' if nothing has."
    )
    current_status: str = Field(description="Where the case stands right now.")
    recommended_next_action: str = Field(
        description="The concrete next step the support team should take."
    )

    @field_validator("*", mode="after")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("summary field must not be empty")
        return cleaned

    def render(self) -> str:
        """Render as a readable internal note."""
        sections = [
            ("Case Overview", self.case_overview),
            ("Key Issue", self.key_issue),
            ("Action Taken", self.action_taken),
            ("Current Status", self.current_status),
            ("Recommended Next Action", self.recommended_next_action),
        ]
        return "\n\n".join(f"{title}\n{'-' * len(title)}\n{body}" for title, body in sections)


# --- Internal application models ---------------------------------------------


class DocumentMeta(BaseModel):
    """Provenance for one ingested file."""

    case_id: str
    source_file: str
    file_type: str
    file_size_bytes: int
    char_count: int
    truncated: bool = False
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseRecord(BaseModel):
    """The complete result of running the workflow over one document."""

    meta: DocumentMeta
    status: ProcessingStatus
    extraction: ExtractedComplaint | None = None
    customer_email: CustomerEmail | None = None
    case_summary: CaseSummary | None = None
    errors: list[str] = Field(default_factory=list)
    task_durations_seconds: dict[str, float] = Field(default_factory=dict)

    @property
    def total_duration_seconds(self) -> float:
        return round(sum(self.task_durations_seconds.values()), 3)


class BatchResult(BaseModel):
    """Aggregate outcome of a full batch run."""

    records: list[CaseRecord] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime
    provider: str
    model: str
    skipped_files: list[str] = Field(default_factory=list)

    @property
    def wall_clock_seconds(self) -> float:
        return round((self.finished_at - self.started_at).total_seconds(), 3)

    def count(self, status: ProcessingStatus) -> int:
        return sum(1 for record in self.records if record.status is status)
