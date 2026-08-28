"""The three AI tasks in the workflow.

Each module here is one LLM step with one responsibility:

* `extraction`      - document              -> `ExtractedComplaint`
* `response_email`  - extracted record      -> `CustomerEmail`
* `case_summary`    - extracted record      -> `CaseSummary`

Splitting them keeps every prompt small and focused, lets the second and third
run concurrently, and makes each step testable on its own. The alternative -
one giant prompt that returns everything - is harder to debug, harder to
validate, and degrades badly on long documents.
"""

from complaint_processor.tasks.case_summary import generate_case_summary
from complaint_processor.tasks.extraction import extract_complaint
from complaint_processor.tasks.response_email import generate_customer_email

__all__ = [
    "extract_complaint",
    "generate_customer_email",
    "generate_case_summary",
]
