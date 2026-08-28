#!/usr/bin/env python3
"""Regenerate the sample documents in `data/`.

The generated files are committed to the repository, so an evaluator never needs
to run this. It exists so the sample set is reproducible and easy to extend, and
so the `.pdf` / `.docx` fixtures are not opaque binaries with no source.

    python scripts/generate_sample_data.py

Requires `reportlab` and `python-docx` (both in requirements.txt).
"""

from __future__ import annotations

import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# --- The case content --------------------------------------------------------
# Deliberately varied: different categories, some resolved and some not, some
# with full contact details and some missing them, different tones, and one
# document that is an enquiry rather than a complaint.

CASES: list[dict[str, object]] = [
    {
        "filename": "complaint_001",
        "format": "txt",
        "title": "CUSTOMER COMPLAINT RECORD",
        "fields": [
            ("Reference", "CMP-2025-0001"),
            ("Date Received", "12 March 2025"),
            ("Customer Name", "Priya Sharma"),
            ("Email", "priya.sharma@example.com"),
            ("Phone", "+91 98765 43210"),
            ("Product / Service", "Prime Home Broadband — 300 Mbps plan"),
        ],
        "sections": [
            (
                "Complaint Description",
                "I was billed twice for the month of February. My account shows two "
                "charges of Rs. 1,499 taken on 3 February and 5 February. I only have "
                "one active connection and one active plan. I have attached copies of "
                "both invoices and my bank statement showing the duplicate debit.",
            ),
            (
                "Issue Details",
                "The duplicate charge was confirmed by the billing team on 8 March. "
                "It appears to have been caused by a failed auto-payment that was then "
                "retried manually while the original transaction was still pending.",
            ),
            (
                "Resolution Provided",
                "A refund of Rs. 1,499 was approved on 10 March and processed to the "
                "original payment method. The customer was informed that it will "
                "reflect within 5 to 7 working days.",
            ),
            ("Escalation", "Not required. Resolved at first line."),
            ("Supporting Information", "Invoice INV-20250203, Invoice INV-20250205, bank statement extract."),
        ],
    },
    {
        "filename": "complaint_002",
        "format": "pdf",
        "title": "CUSTOMER COMPLAINT RECORD",
        "fields": [
            ("Reference", "CMP-2025-0002"),
            ("Date Received", "18 March 2025"),
            ("Customer Name", "Rahul Verma"),
            ("Email", "rahul.verma88@example.com"),
            ("Phone", "+91 90123 45678"),
            ("Product / Service", "Express Delivery — order ORD-77821"),
        ],
        "sections": [
            (
                "Complaint Description",
                "This is the third time I am writing about order ORD-77821. It was "
                "promised for delivery on 6 March under your Express guarantee. It is "
                "now 18 March and the tracking page has said 'out for dispatch' for "
                "eleven days. Nobody from your side has called me back despite two "
                "previous tickets. This is completely unacceptable and I want this "
                "escalated to a manager immediately.",
            ),
            (
                "Issue Details",
                "The consignment appears to be stuck at the regional sorting hub. The "
                "courier partner has not provided a scan update since 7 March. The "
                "customer has already been charged the Express delivery premium.",
            ),
            ("Resolution Provided", ""),
            (
                "Escalation",
                "Customer has explicitly requested escalation to a supervisor and has "
                "mentioned raising the matter with the consumer forum if not resolved "
                "this week.",
            ),
            ("Supporting Information", "Screenshot of tracking page attached. Previous ticket IDs: TKT-4411, TKT-4622."),
        ],
    },
    {
        "filename": "complaint_003",
        "format": "docx",
        "title": "PRODUCT SUPPORT CASE FORM",
        "table_fields": [
            ("Reference", "CMP-2025-0003"),
            ("Date Received", "21 March 2025"),
            ("Customer Name", "Ananya Iyer"),
            ("Email", "ananya.iyer@example.com"),
            ("Phone", "080-4455-9012"),
            ("Product / Service", "AeroBlend 750W Mixer Grinder"),
            ("Warranty Status", "In warranty until 14 Nov 2025"),
        ],
        "sections": [
            (
                "Complaint Description",
                "The mixer grinder started making a loud grinding noise and then "
                "stopped working entirely after about six weeks of normal household "
                "use. There is a burning smell from the motor housing. The unit is "
                "still under warranty and I would like a replacement rather than a "
                "repair, since this is clearly a manufacturing defect.",
            ),
            (
                "Issue Details",
                "Technician visited on 20 March and confirmed the motor winding has "
                "failed. The report notes this is a known issue on units from the "
                "November 2024 production batch.",
            ),
            (
                "Resolution Provided",
                "A replacement unit has been approved under warranty and the request "
                "is currently being processed by the service centre. Pickup of the "
                "faulty unit is scheduled for 24 March.",
            ),
            ("Escalation", "Not required at this stage."),
            ("Supporting Information", "Technician report TR-9087 and purchase invoice enclosed."),
        ],
    },
    {
        "filename": "complaint_004",
        "format": "txt",
        "title": "SUPPORT TICKET",
        "fields": [
            ("Reference", "CMP-2025-0004"),
            ("Date Received", "22 March 2025"),
            ("Customer Name", "Daniel Okonkwo"),
            ("Email", "d.okonkwo@example.org"),
            ("Phone", ""),
            ("Product / Service", "MyAccount customer portal"),
        ],
        "sections": [
            (
                "Complaint Description",
                "I cannot log in to my account. Every time I enter my password the "
                "page reloads and says 'access denied'. I have tried resetting the "
                "password twice and I never receive the OTP on email. I need access "
                "because my renewal is due on 30 March.",
            ),
            (
                "Issue Details",
                "Password reset emails appear to be failing for this account. Account "
                "was locked automatically after five failed sign-in attempts. No "
                "engineering investigation has been opened yet.",
            ),
            ("Resolution Provided", ""),
            ("Escalation", "Not requested by the customer."),
            ("Supporting Information", "None provided."),
        ],
    },
    {
        "filename": "complaint_005",
        "format": "pdf",
        "title": "CUSTOMER COMPLAINT RECORD",
        "fields": [
            ("Reference", "CMP-2025-0005"),
            ("Date Received", "25 March 2025"),
            ("Customer Name", "Meera Krishnan"),
            ("Email", "meera.k@example.com"),
            ("Phone", "+91 99887 76655"),
            ("Product / Service", "Annual Subscription — Studio Pro"),
        ],
        "sections": [
            (
                "Complaint Description",
                "I cancelled my Studio Pro subscription within the 14-day cooling off "
                "period on 11 March, but I have still not received my refund of "
                "Rs. 8,999. Your policy page says refunds are processed in 7 working "
                "days. It has been two weeks. I would like my money back please.",
            ),
            (
                "Issue Details",
                "Cancellation was correctly recorded on 11 March. The refund request "
                "was created but is sitting in the finance queue awaiting approval and "
                "has not been actioned.",
            ),
            (
                "Resolution Provided",
                "Finance team has been asked to prioritise the refund. The customer "
                "has been told the refund is under review and will be confirmed once "
                "approved.",
            ),
            ("Escalation", "Not yet escalated, but the delay is outside policy."),
            ("Supporting Information", "Cancellation confirmation email attached."),
        ],
    },
    {
        "filename": "complaint_006",
        "format": "md",
        "title": "CUSTOMER ENQUIRY",
        "fields": [
            ("Reference", "ENQ-2025-0006"),
            ("Date Received", "26 March 2025"),
            ("Customer Name", "James Whitfield"),
            ("Email", "j.whitfield@example.co.uk"),
            ("Phone", "+44 7700 900123"),
            ("Product / Service", "Business Plus plan"),
        ],
        "sections": [
            (
                "Enquiry Description",
                "Hello, this is not a complaint. I'd just like some clarification "
                "before I upgrade. If I move from the Standard plan to Business Plus "
                "mid-cycle, am I charged the full month or is it pro-rated? And does "
                "the seat count reset on the upgrade date or on my usual billing date? "
                "Thanks very much for your help.",
            ),
            (
                "Issue Details",
                "Straightforward pre-sales question about pro-rated billing on a "
                "mid-cycle plan upgrade. No service fault reported.",
            ),
            (
                "Resolution Provided",
                "Billing team confirmed that mid-cycle upgrades are pro-rated and that "
                "the seat count resets on the existing billing date. This was sent to "
                "the customer on 26 March.",
            ),
            ("Escalation", "Not required."),
            ("Supporting Information", "None."),
        ],
    },
    {
        "filename": "complaint_007",
        "format": "txt",
        "title": "COMPLAINT — WEB FORM SUBMISSION",
        "fields": [
            ("Reference", "CMP-2025-0007"),
            ("Date Received", "27 March 2025"),
        ],
        "sections": [
            (
                "Complaint Description",
                "Your mobile app has crashed every single time I try to open the "
                "reports tab since the update last Tuesday. I get a blank screen and "
                "then it closes. I have reinstalled twice. I run a small business and "
                "I cannot access my own sales data. This is costing me money and I am "
                "extremely frustrated. I have been a customer for four years and this "
                "is the worst support experience I have had.",
            ),
            (
                "Issue Details",
                "Reproducible crash on the reports screen following release 4.2.0. "
                "Several similar reports received the same week, suggesting a "
                "regression rather than a device-specific fault. Engineering has been "
                "notified but no fix is available yet.",
            ),
            ("Resolution Provided", ""),
            (
                "Escalation",
                "Escalated to the mobile engineering team as a possible release "
                "regression. Customer is asking for a callback from a manager.",
            ),
            (
                "Supporting Information",
                "Customer attached a crash log file and two screenshots. Note: the "
                "web form was submitted without contact details.",
            ),
        ],
    },
    {
        "filename": "complaint_008",
        "format": "docx",
        "title": "SERVICE FEEDBACK CASE FORM",
        "table_fields": [
            ("Reference", "CMP-2025-0008"),
            ("Date Received", "28 March 2025"),
            ("Customer Name", "Fatima Al-Rashid"),
            ("Email", "fatima.alrashid@example.com"),
            ("Phone", "+971 50 123 4567"),
            ("Product / Service", "In-store installation service"),
        ],
        "sections": [
            (
                "Complaint Description",
                "I want to raise a complaint about the installation appointment on "
                "19 March. The engineer arrived three hours outside the agreed slot "
                "without calling ahead, and I had taken the day off work. The "
                "installation itself was fine, but the communication was very poor and "
                "the call centre staff were quite dismissive when I phoned to ask "
                "where the engineer was.",
            ),
            (
                "Issue Details",
                "Scheduling system did not send the delay notification. Call centre "
                "handling of the enquiry was reviewed and found to fall below the "
                "expected standard.",
            ),
            (
                "Resolution Provided",
                "The service manager called the customer on 21 March to apologise. A "
                "goodwill credit of AED 150 was applied to the account and the call "
                "centre agent has been given coaching. The customer confirmed she was "
                "satisfied with the outcome and thanked the manager for following up.",
            ),
            ("Escalation", "Handled by the service manager. Now closed."),
            ("Supporting Information", "Call recording reference CR-3391."),
        ],
    },
]


# --- Renderers ---------------------------------------------------------------


def _plain_text_body(case: dict[str, object]) -> str:
    lines: list[str] = [str(case["title"]), "=" * len(str(case["title"])), ""]

    for label, value in case.get("fields", []):  # type: ignore[union-attr]
        lines.append(f"{label}: {value}")
    lines.append("")

    for heading, body in case["sections"]:  # type: ignore[index]
        lines.append(f"{heading}:")
        lines.append(body if body else "(none recorded)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _markdown_body(case: dict[str, object]) -> str:
    lines: list[str] = [f"# {case['title']}", ""]

    for label, value in case.get("fields", []):  # type: ignore[union-attr]
        lines.append(f"- **{label}:** {value}")
    lines.append("")

    for heading, body in case["sections"]:  # type: ignore[index]
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(body if body else "_(none recorded)_")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_txt(case: dict[str, object], path: Path) -> None:
    path.write_text(_plain_text_body(case), encoding="utf-8")


def write_md(case: dict[str, object], path: Path) -> None:
    path.write_text(_markdown_body(case), encoding="utf-8")


def write_pdf(case: dict[str, object], path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "CaseHeading", parent=styles["Heading2"], spaceBefore=10, spaceAfter=4, fontSize=11
    )
    body = ParagraphStyle("CaseBody", parent=styles["BodyText"], fontSize=10, leading=14)

    story: list[object] = [Paragraph(str(case["title"]), styles["Title"]), Spacer(1, 6)]

    for label, value in case.get("fields", []):  # type: ignore[union-attr]
        story.append(Paragraph(f"<b>{label}:</b> {value}", body))
    story.append(Spacer(1, 8))

    for section_heading, section_body in case["sections"]:  # type: ignore[index]
        story.append(Paragraph(section_heading, heading))
        story.append(Paragraph(section_body or "(none recorded)", body))

    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=str(case["title"]),
    ).build(story)


def write_docx(case: dict[str, object], path: Path) -> None:
    import docx

    document = docx.Document()
    document.add_heading(str(case["title"]), level=1)

    # Field data goes in a table, which exercises the DOCX loader's table handling.
    fields = case.get("table_fields", [])  # type: ignore[union-attr]
    if fields:
        table = document.add_table(rows=0, cols=2)
        table.style = "Table Grid"
        for label, value in fields:
            row = table.add_row().cells
            row[0].text = str(label)
            row[1].text = str(value)
        document.add_paragraph("")

    for heading, body in case["sections"]:  # type: ignore[index]
        document.add_heading(heading, level=2)
        document.add_paragraph(body or "(none recorded)")

    document.save(str(path))


WRITERS = {"txt": write_txt, "md": write_md, "pdf": write_pdf, "docx": write_docx}


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for case in CASES:
        fmt = str(case["format"])
        path = DATA_DIR / f"{case['filename']}.{fmt}"
        WRITERS[fmt](case, path)
        print(f"  wrote {path.relative_to(DATA_DIR.parent)}")

    # Deliberate edge cases, so error handling can be demonstrated on a real run.
    empty = DATA_DIR / "edge_case_empty_document.txt"
    empty.write_text("", encoding="utf-8")
    print(f"  wrote {empty.relative_to(DATA_DIR.parent)}  (intentionally empty)")

    unsupported = DATA_DIR / "edge_case_unsupported_format.xlsx"
    unsupported.write_bytes(b"not a real spreadsheet - present to test format filtering")
    print(f"  wrote {unsupported.relative_to(DATA_DIR.parent)}  (intentionally unsupported)")

    print(f"\nSample data written to {DATA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
