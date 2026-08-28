"""Offline provider — a deterministic, rule-based stand-in for a real LLM.

This is **not** an AI model. It is a heuristic implementation of the same
`LLMClient` interface, built from a section parser, regular expressions and
weighted keyword scoring. It exists for three practical reasons:

1. An evaluator can clone the repository and run the full pipeline end to end
   with no API key and no spend (`python run.py --provider mock`).
2. The unit tests can exercise the real workflow, batching, error handling and
   reporting code without network access or non-determinism.
3. It proves the provider abstraction is genuinely an abstraction — the workflow
   above it does not change by one line when the backend does.

Its accuracy comes from the fact that business complaint records are usually
*semi-structured* (labelled fields and headed sections). It reads the
`<document>` and `<extracted_data>` blocks the prompt builders emit, so it sees
exactly the same input a real provider would. On genuinely free-form prose a
real model will do much better, which is the point of the comparison.
"""

from __future__ import annotations

import json
import re
import time

from complaint_processor.exceptions import LLMResponseError
from complaint_processor.llm.base import LLMClient, SchemaT
from complaint_processor.logging_setup import get_logger
from complaint_processor.models import (
    CaseStatus,
    CaseSummary,
    ComplaintCategory,
    CustomerEmail,
    ExtractedComplaint,
    Priority,
    Sentiment,
)

logger = get_logger(__name__)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")

# Text meaning "nothing here", however the source document chose to spell it.
_EMPTY_VALUES = re.compile(
    r"^\(?\s*(none|none\.|none recorded|none provided|not provided|n/?a|nil|-+)\s*\)?\.?$",
    re.IGNORECASE,
)

# --- Section and field parsing -----------------------------------------------

# Canonical section names -> the label variants that introduce them.
_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "description": ("complaint description", "enquiry description", "issue description", "description"),
    "issue_details": ("issue details", "details"),
    "resolution": ("resolution provided", "resolution", "action taken"),
    "escalation": ("escalation", "escalation information"),
    "supporting": ("supporting information", "supporting documents", "attachments"),
}

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("customer name", "name", "raised by", "customer"),
    "email": ("email", "email address", "e-mail"),
    "phone": ("phone", "phone number", "contact number", "mobile"),
    "product": ("product / service", "product/service", "product", "service", "item"),
    "reference": ("reference", "ref", "case id", "ticket"),
}

_ALL_SECTION_LABELS = {
    alias for aliases in _SECTION_ALIASES.values() for alias in aliases
}
_ALL_FIELD_LABELS = {alias for aliases in _FIELD_ALIASES.values() for alias in aliases}

# Strips markdown/heading decoration from a label line: "## **Label:**" -> "Label"
_LABEL_LINE_RE = re.compile(r"^\s*#{0,6}\s*\**\s*([A-Za-z][A-Za-z /'-]{2,40}?)\s*\**\s*:?\s*$")
_INLINE_FIELD_RE = re.compile(
    r"^\s*[-*]?\s*\**\s*([A-Za-z][A-Za-z /'-]{2,40}?)\s*\**\s*[:|]\s*(.*)$"
)


def _canonical(label: str, aliases: dict[str, tuple[str, ...]]) -> str | None:
    normalised = label.strip().lower().rstrip(":").strip()
    for canonical_name, variants in aliases.items():
        if normalised in variants:
            return canonical_name
    return None


def _clean_value(value: str) -> str:
    value = value.strip().strip("*_").strip()
    if not value or _EMPTY_VALUES.match(value):
        return ""
    return value


def _parse_document(document: str) -> tuple[dict[str, str], dict[str, str]]:
    """Split a semi-structured document into `(fields, sections)`.

    `fields` are single-line "Label: value" pairs (also matching the
    "Label | value" form the DOCX loader produces for table rows).
    `sections` are multi-line blocks introduced by a known heading.
    """
    fields: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for line in document.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # A bare/heading-style label line opens a new section.
        heading_match = _LABEL_LINE_RE.match(stripped)
        if heading_match:
            candidate = heading_match.group(1).strip().lower()
            if candidate in _ALL_SECTION_LABELS:
                current_section = _canonical(candidate, _SECTION_ALIASES)
                if current_section:
                    sections.setdefault(current_section, [])
                continue

        # An inline "Label: value" line is either a field or a one-line section.
        inline_match = _INLINE_FIELD_RE.match(stripped)
        if inline_match:
            label, value = inline_match.group(1), inline_match.group(2)
            lowered = label.strip().lower()

            if lowered in _ALL_FIELD_LABELS:
                key = _canonical(lowered, _FIELD_ALIASES)
                if key and key not in fields:
                    fields[key] = _clean_value(value)
                current_section = None
                continue

            if lowered in _ALL_SECTION_LABELS:
                current_section = _canonical(lowered, _SECTION_ALIASES)
                if current_section:
                    sections.setdefault(current_section, [])
                    if _clean_value(value):
                        sections[current_section].append(_clean_value(value))
                continue

        if current_section:
            sections[current_section].append(stripped)

    merged = {name: _clean_value(" ".join(lines)) for name, lines in sections.items()}
    return fields, merged


# --- Keyword rules -----------------------------------------------------------

# Weighted keywords per category. Scored against the description and issue
# details only — never the resolution, because "a refund was issued" describes
# the fix, not the complaint.
_CATEGORY_KEYWORDS: dict[ComplaintCategory, tuple[tuple[str, int], ...]] = {
    ComplaintCategory.BILLING: (
        ("billed twice", 3), ("duplicate charge", 3), ("duplicate debit", 3),
        ("overcharge", 3), ("billing", 2), ("invoice", 1), ("charged", 1),
        ("charges", 1), ("payment", 1), ("auto-payment", 2),
    ),
    ComplaintCategory.DELIVERY: (
        ("delivery", 3), ("delivered", 2), ("dispatch", 2), ("courier", 3),
        ("shipment", 3), ("consignment", 3), ("tracking", 2), ("parcel", 2),
        ("sorting hub", 2),
    ),
    ComplaintCategory.PRODUCT_DEFECT: (
        ("manufacturing defect", 3), ("defect", 3), ("stopped working", 3),
        ("burning smell", 3), ("faulty", 3), ("malfunction", 3), ("broken", 2),
        ("damaged", 2), ("not working", 2), ("failed", 1),
    ),
    ComplaintCategory.WARRANTY: (
        ("under warranty", 2), ("warranty", 1), ("guarantee", 1),
    ),
    ComplaintCategory.REFUND: (
        ("refund", 3), ("money back", 3), ("reimburse", 3), ("chargeback", 3),
        ("cancelled my", 2), ("cooling off", 2),
    ),
    ComplaintCategory.ACCOUNT_ACCESS: (
        ("cannot log in", 3), ("log in", 2), ("login", 3), ("sign in", 2),
        ("password", 3), ("access denied", 3), ("account locked", 3),
        ("otp", 2), ("locked", 1),
    ),
    ComplaintCategory.TECHNICAL_ISSUE: (
        ("crash", 3), ("crashed", 3), ("blank screen", 3), ("regression", 2),
        ("bug", 2), ("error", 2), ("app", 1), ("reinstall", 2), ("timeout", 2),
        ("server", 1), ("connectivity", 2),
    ),
    ComplaintCategory.SERVICE_QUALITY: (
        ("dismissive", 3), ("rude", 3), ("unprofessional", 3),
        ("communication was", 2), ("call centre", 2), ("staff", 2),
        ("outside the agreed slot", 3), ("without calling", 2), ("waiting", 1),
    ),
}

# Escalation is decided from the escalation section when there is one, because
# the literal word "Escalation" appears as a *label* in almost every form.
_ESCALATION_NEGATIVE = (
    "not required", "not requested", "not yet escalated", "not escalated",
    "none", "no escalation", "now closed", "handled by", "resolved at first line",
)
_ESCALATION_POSITIVE = (
    "escalat", "supervisor", "manager", "consumer forum", "consumer court",
    "legal", "callback", "call back",
)
_ESCALATION_IN_DESCRIPTION = (
    "escalated immediately", "want this escalated", "raise this to a manager",
    "third time", "no response", "unacceptable", "consumer forum",
)

_IN_PROGRESS_KEYWORDS = (
    "being processed", "under review", "in progress", "investigating",
    "has been asked", "awaiting", "scheduled for", "prioritise", "prioritize",
)
_RESOLVED_KEYWORDS = (
    "refund", "replaced", "resolved", "closed", "completed", "settled",
    "credited", "apolog", "confirmed", "credit of", "goodwill",
)

_ATTACHMENT_KEYWORDS = (
    "attach", "enclosed", "screenshot", "invoice", "receipt", "photo",
    "log file", "recording", "statement", "report", "evidence", "copy",
)

_NEGATIVE_KEYWORDS = (
    "frustrat", "disappoint", "angry", "unacceptable", "worst", "terrible",
    "furious", "very poor", "dismissive", "costing me money",
)
_STRONG_NEGATIVE_KEYWORDS = (
    "extremely frustrated", "completely unacceptable", "worst", "furious",
)
_POSITIVE_KEYWORDS = (
    "thank", "appreciate", "happy", "satisfied", "pleased", "not a complaint",
)

_ENQUIRY_MARKERS = (
    "not a complaint", "enquiry description", "customer enquiry",
    "clarification before", "pre-sales",
)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _score_category(text: str) -> ComplaintCategory:
    """Pick the highest-scoring category; fall back to OTHER on a total miss."""
    scores: dict[ComplaintCategory, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(weight for keyword, weight in keywords if keyword in text)
        if score:
            scores[category] = score

    if not scores:
        return ComplaintCategory.OTHER
    # max() over (score, name) keeps ties deterministic run to run.
    return max(scores, key=lambda category: (scores[category], category.value))


class MockClient(LLMClient):
    """Rule-based `LLMClient` implementation for offline runs and tests."""

    provider_name = "mock"

    def __init__(self, *, model: str = "offline-rule-based", temperature: float = 0.0) -> None:
        super().__init__(model=model, temperature=temperature)
        logger.warning(
            "Using the OFFLINE mock provider: output is rule-based, not model-generated."
        )

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        task_name: str,
    ) -> SchemaT:
        started = time.perf_counter()

        document = _extract_block(user_prompt, "document")
        extracted_json = _extract_block(user_prompt, "extracted_data")

        if schema is ExtractedComplaint:
            result: object = self._build_extraction(document)
        elif schema is CustomerEmail:
            result = self._build_email(extracted_json)
        elif schema is CaseSummary:
            result = self._build_summary(extracted_json)
        else:  # pragma: no cover - guards against a new task forgetting the mock
            raise LLMResponseError(f"Mock provider has no rule for schema {schema.__name__}")

        # Rough token accounting so the run summary stays meaningful offline.
        self._record_usage(len(user_prompt) // 4, 200)
        logger.debug(
            "mock completed task '%s' in %.3fs", task_name, time.perf_counter() - started
        )
        return result  # type: ignore[return-value]

    # --- Task 1 ---------------------------------------------------------------

    def _build_extraction(self, document: str) -> ExtractedComplaint:
        fields, sections = _parse_document(document)
        lower_document = document.lower()

        description = sections.get("description", "")
        issue_details = sections.get("issue_details", "")
        resolution = sections.get("resolution", "")
        escalation_text = sections.get("escalation", "").lower()
        supporting_text = sections.get("supporting", "")

        # The complaint itself, not the fix, is what determines the category.
        subject_text = f"{description} {issue_details}".lower().strip()
        if not subject_text:
            subject_text = lower_document

        is_enquiry = _contains_any(lower_document, _ENQUIRY_MARKERS)
        category = (
            ComplaintCategory.GENERAL_ENQUIRY if is_enquiry else _score_category(subject_text)
        )

        escalation = self._decide_escalation(escalation_text, description.lower())
        status = self._decide_status(escalation, resolution.lower(), lower_document)
        sentiment = self._decide_sentiment(subject_text, escalation, is_enquiry)
        priority = self._decide_priority(escalation, status, sentiment)

        supporting = bool(supporting_text) and _contains_any(
            supporting_text.lower(), _ATTACHMENT_KEYWORDS
        )
        if not supporting:
            supporting = _contains_any(description.lower(), ("attach", "enclosed"))

        # Fall back to a document-wide scan when the form had no labelled field.
        email_match = _EMAIL_RE.search(fields.get("email") or document)
        phone_source = fields.get("phone") or ""
        phone_match = _PHONE_RE.search(phone_source) if phone_source else None

        notes = self._build_notes(fields, resolution)

        return ExtractedComplaint(
            customer_name=fields.get("name") or None,
            email=email_match.group(0) if email_match else None,
            phone_number=phone_match.group(0) if phone_match else None,
            product_or_service=fields.get("product") or None,
            complaint_category=category,
            issue_description=self._pick_issue_description(description, issue_details, document),
            resolution_provided=resolution or None,
            is_complaint=not is_enquiry,
            escalation_required=escalation,
            supporting_document_available=supporting,
            overall_case_status=status,
            priority=priority,
            customer_sentiment=sentiment,
            extraction_notes=notes,
        )

    @staticmethod
    def _decide_escalation(escalation_text: str, description: str) -> bool:
        if escalation_text:
            # Negative markers win: "Not required." must not match on "manager".
            if _contains_any(escalation_text, _ESCALATION_NEGATIVE):
                return False
            if _contains_any(escalation_text, _ESCALATION_POSITIVE):
                return True
        return _contains_any(description, _ESCALATION_IN_DESCRIPTION)

    @staticmethod
    def _decide_status(escalation: bool, resolution: str, document: str) -> CaseStatus:
        if escalation:
            return CaseStatus.ESCALATED
        if not resolution:
            return CaseStatus.OPEN
        # Checked before "resolved": "the refund is being processed" is not done.
        if _contains_any(resolution, _IN_PROGRESS_KEYWORDS):
            return CaseStatus.IN_PROGRESS
        if "now closed" in document or "case is closed" in document:
            return CaseStatus.CLOSED
        if _contains_any(resolution, _RESOLVED_KEYWORDS):
            return CaseStatus.RESOLVED
        return CaseStatus.IN_PROGRESS

    @staticmethod
    def _decide_sentiment(text: str, escalation: bool, is_enquiry: bool) -> Sentiment:
        if _contains_any(text, _STRONG_NEGATIVE_KEYWORDS):
            return Sentiment.VERY_NEGATIVE
        if _contains_any(text, _NEGATIVE_KEYWORDS):
            return Sentiment.VERY_NEGATIVE if escalation else Sentiment.NEGATIVE
        if is_enquiry or _contains_any(text, _POSITIVE_KEYWORDS):
            return Sentiment.POSITIVE
        return Sentiment.NEUTRAL

    @staticmethod
    def _decide_priority(
        escalation: bool, status: CaseStatus, sentiment: Sentiment
    ) -> Priority:
        if escalation:
            return Priority.CRITICAL if sentiment is Sentiment.VERY_NEGATIVE else Priority.HIGH
        if status in (CaseStatus.RESOLVED, CaseStatus.CLOSED):
            return Priority.LOW
        if status is CaseStatus.OPEN:
            return Priority.MEDIUM
        return Priority.MEDIUM

    @staticmethod
    def _build_notes(fields: dict[str, str], resolution: str) -> str:
        missing = [
            label
            for key, label in (("name", "customer name"), ("email", "email"), ("phone", "phone number"))
            if not fields.get(key)
        ]
        parts = ["Generated by the offline rule-based provider."]
        if missing:
            parts.append(f"Document does not state: {', '.join(missing)}.")
        if not resolution:
            parts.append("No resolution recorded yet.")
        return " ".join(parts)

    @staticmethod
    def _pick_issue_description(description: str, issue_details: str, document: str) -> str:
        for candidate in (description, issue_details):
            if len(candidate) > 25:
                return candidate[:800]

        prose = [
            line.strip()
            for line in document.splitlines()
            if len(line.strip()) > 40 and ":" not in line[:20]
        ]
        if prose:
            return max(prose, key=len)[:800]
        return (document[:300] or "No issue description could be identified.").strip()

    # --- Tasks 2 and 3 --------------------------------------------------------

    @staticmethod
    def _load_extraction(extracted_json: str) -> ExtractedComplaint:
        if not extracted_json:
            raise LLMResponseError("Mock provider expected an <extracted_data> block")
        try:
            return ExtractedComplaint.model_validate(json.loads(extracted_json))
        except Exception as exc:  # noqa: BLE001
            raise LLMResponseError(f"Mock provider could not read extracted data: {exc}") from exc

    def _build_email(self, extracted_json: str) -> CustomerEmail:
        data = self._load_extraction(extracted_json)
        topic = data.product_or_service or data.complaint_category.value.lower()

        if data.is_complaint:
            opening = (
                f"Thank you for contacting us about {topic}. I am sorry for the "
                "inconvenience this has caused, and I appreciate you taking the time "
                "to bring it to our attention."
            )
        else:
            opening = (
                f"Thank you for getting in touch about {topic}. I am happy to clarify "
                "this for you."
            )

        paragraphs = [
            opening,
            f"So that we are clear on what you reported: “{data.issue_description}”",
        ]

        if data.resolution_provided:
            paragraphs.append(f"Here is what has been done so far. {data.resolution_provided}")
        else:
            paragraphs.append(
                "Your case is currently open with our support team and no resolution "
                "has been recorded yet. We are working on it and will update you as "
                "soon as there is progress."
            )

        if data.escalation_required:
            paragraphs.append(
                "Given the circumstances, your case has been escalated to a senior "
                "support specialist, who will follow up with you directly."
            )

        paragraphs.append(
            f"The current status of your case is: {data.overall_case_status.value}. "
            "If anything above is not correct, or you have further questions, please "
            "reply to this email and we will pick it up straight away."
        )

        return CustomerEmail(
            subject=(
                f"Your {data.complaint_category.value.lower()} case — "
                f"{data.overall_case_status.value}"
            ),
            greeting=f"Dear {data.display_name},",
            body_paragraphs=paragraphs,
            closing="Kind regards,",
            sender_name="Customer Support Team",
        )

    def _build_summary(self, extracted_json: str) -> CaseSummary:
        data = self._load_extraction(extracted_json)
        subject = data.product_or_service or "the reported item"
        kind = "complaint" if data.is_complaint else "enquiry"

        if data.escalation_required:
            next_action = (
                "Assign to a senior specialist and make contact with the customer "
                "within 24 hours."
            )
        elif data.overall_case_status in (CaseStatus.RESOLVED, CaseStatus.CLOSED):
            next_action = "Confirm the customer is satisfied, then close the case."
        elif not data.resolution_provided:
            next_action = (
                "Investigate the reported issue and send the customer an initial "
                "response with an expected timeline."
            )
        else:
            next_action = (
                "Chase the owning team for completion and update the customer on "
                "progress."
            )

        return CaseSummary(
            case_overview=(
                f"{data.complaint_category.value} {kind} raised by {data.display_name} "
                f"regarding {subject}."
            ),
            key_issue=data.issue_description,
            action_taken=data.resolution_provided or "No action recorded.",
            current_status=(
                f"{data.overall_case_status.value}. Priority {data.priority.value}; "
                f"customer sentiment {data.customer_sentiment.value.lower()}."
            ),
            recommended_next_action=next_action,
        )


def _extract_block(prompt: str, tag: str) -> str:
    """Pull the contents of a `<tag>...</tag>` block out of the prompt."""
    match = re.search(rf"<{tag}>(.*?)</{tag}>", prompt, re.DOTALL)
    return match.group(1).strip() if match else ""
