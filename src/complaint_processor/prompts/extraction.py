"""Prompts for Task 1 — structured information extraction.

Design notes (prompt engineering):
- The system prompt fixes the *role* and the *rules*; the user prompt carries
  only data. Keeping them apart means the rules cannot be diluted by document
  content, and it makes prompt-injection from a hostile document much harder.
- The document is wrapped in explicit `<document>` delimiters so the model can
  always tell instructions from input.
- The anti-hallucination rule is stated as a concrete instruction ("use null")
  rather than a vague plea ("be accurate"), because it needs to map onto an
  action the model can actually take within the schema.
"""

from __future__ import annotations

EXTRACTION_SYSTEM_PROMPT = """\
You are a meticulous customer-support case analyst working inside an automated \
document-processing pipeline. Your job is to read one customer complaint document \
and convert it into a structured case record.

Rules you must follow:
1. Ground every field in the document. Never invent a name, email, phone number, \
order ID, date, or resolution that is not written in the document.
2. If a value is genuinely absent, return null for that field. Do not guess, and \
do not substitute placeholder text such as "N/A" or "unknown".
3. Copy contact details (email, phone) exactly as they appear. Do not reformat them.
4. `issue_description` must be a neutral, factual restatement in one to three \
sentences. No advice, no apology, no speculation about cause.
5. `resolution_provided` describes only what has *already* been done. If the \
document records no action yet, return null.
6. `escalation_required` is true when the document asks for escalation, records \
an escalation, threatens further action, or describes a severe unresolved issue.
7. `supporting_document_available` is true only when the document explicitly \
mentions an attachment or supporting evidence.
8. Choose exactly one value from each provided enumeration. Pick the closest \
match; use "Other" only when nothing fits.
9. Use `extraction_notes` to record genuine ambiguity or missing information. \
Return null when the document was clear.

Return only the structured record. No commentary."""


def build_extraction_user_prompt(*, source_file: str, document_text: str) -> str:
    """Build the user message for the extraction task."""
    return f"""\
Extract the structured case record from the customer complaint document below.

Source file: {source_file}

<document>
{document_text}
</document>"""
