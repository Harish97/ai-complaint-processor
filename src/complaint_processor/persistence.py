"""Writing per-case artefacts to the `output/` tree.

One function per output family, so the batch runner stays about orchestration
and this module owns everything about on-disk layout and formatting.
"""

from __future__ import annotations

import json
from pathlib import Path

from complaint_processor.config import Settings
from complaint_processor.logging_setup import get_logger
from complaint_processor.models import CaseRecord

logger = get_logger(__name__)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_case_outputs(record: CaseRecord, settings: Settings) -> list[Path]:
    """Persist everything this record produced. Returns the paths written.

    Partial records are still written: a document whose email generation failed
    should not lose its perfectly good extraction and summary.
    """
    case_id = record.meta.case_id
    written: list[Path] = []

    # 1. Structured data — the validated record, plus provenance and any errors.
    structured_path = settings.structured_data_dir / f"{case_id}.json"
    payload = {
        "case_id": case_id,
        "source_file": record.meta.source_file,
        "processing_status": record.status.value,
        "metadata": json.loads(record.meta.model_dump_json()),
        "extraction": (
            json.loads(record.extraction.model_dump_json()) if record.extraction else None
        ),
        "task_durations_seconds": record.task_durations_seconds,
        "errors": record.errors,
    }
    _write_text(structured_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    written.append(structured_path)

    # 2. Customer response email — rendered as a sendable plain-text message.
    if record.customer_email is not None:
        email_path = settings.customer_emails_dir / f"{case_id}.txt"
        _write_text(email_path, record.customer_email.render())
        written.append(email_path)

    # 3. Internal case summary — readable note for a support manager.
    if record.case_summary is not None:
        summary_path = settings.case_summaries_dir / f"{case_id}.md"
        header = (
            f"# Case Summary — {case_id}\n\n"
            f"**Source file:** {record.meta.source_file}  \n"
        )
        if record.extraction is not None:
            header += (
                f"**Category:** {record.extraction.complaint_category.value}  \n"
                f"**Priority:** {record.extraction.priority.value}  \n"
                f"**Escalation required:** "
                f"{'Yes' if record.extraction.escalation_required else 'No'}  \n"
            )
        _write_text(summary_path, header + "\n" + record.case_summary.render() + "\n")
        written.append(summary_path)

    logger.debug("Wrote %d output file(s) for %s", len(written), case_id)
    return written
