"""End-to-end tests for batch processing, persistence and the final report."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from complaint_processor.batch import run_batch
from complaint_processor.models import ProcessingStatus
from complaint_processor.reporting import (
    REPORT_COLUMNS,
    write_final_report,
    write_run_manifest,
)


def _seed(input_dir: Path, sample_text: str, count: int = 3) -> None:
    for index in range(1, count + 1):
        (input_dir / f"complaint_{index:03d}.txt").write_text(sample_text, encoding="utf-8")


def test_batch_processes_every_document(settings, mock_client, sample_complaint_text):
    _seed(settings.input_dir, sample_complaint_text, count=5)

    result = run_batch(client=mock_client, settings=settings)

    assert len(result.records) == 5
    assert result.count(ProcessingStatus.SUCCESS) == 5


def test_batch_writes_all_three_output_families(settings, mock_client, sample_complaint_text):
    _seed(settings.input_dir, sample_complaint_text, count=2)

    run_batch(client=mock_client, settings=settings)

    assert len(list(settings.structured_data_dir.glob("*.json"))) == 2
    assert len(list(settings.customer_emails_dir.glob("*.txt"))) == 2
    assert len(list(settings.case_summaries_dir.glob("*.md"))) == 2


def test_structured_output_is_validated_json_not_raw_text(
    settings, mock_client, sample_complaint_text
):
    """The brief forbids simply saving the raw LLM response."""
    _seed(settings.input_dir, sample_complaint_text, count=1)

    run_batch(client=mock_client, settings=settings)

    payload = json.loads((settings.structured_data_dir / "complaint_001.json").read_text())

    assert payload["processing_status"] == "SUCCESS"
    assert payload["extraction"]["customer_name"] == "Priya Sharma"
    assert payload["metadata"]["source_file"] == "complaint_001.txt"
    assert payload["errors"] == []


def test_results_are_sorted_deterministically(settings, mock_client, sample_complaint_text):
    """Futures finish out of order; the report must not."""
    _seed(settings.input_dir, sample_complaint_text, count=6)

    result = run_batch(client=mock_client, settings=settings)

    names = [record.meta.source_file for record in result.records]
    assert names == sorted(names)


def test_one_bad_document_does_not_stop_the_batch(
    settings, mock_client, sample_complaint_text
):
    _seed(settings.input_dir, sample_complaint_text, count=2)
    (settings.input_dir / "empty.txt").write_text("", encoding="utf-8")
    (settings.input_dir / "notes.xlsx").write_bytes(b"unsupported")

    result = run_batch(client=mock_client, settings=settings)

    assert result.count(ProcessingStatus.SUCCESS) == 2
    assert result.count(ProcessingStatus.FAILED) == 1  # the empty file
    assert result.skipped_files == ["notes.xlsx"]  # unsupported, reported not hidden


def test_empty_input_folder_is_handled_gracefully(settings, mock_client):
    result = run_batch(client=mock_client, settings=settings)

    assert result.records == []
    assert result.wall_clock_seconds >= 0


def test_limit_flag_caps_the_batch(settings, mock_client, sample_complaint_text):
    _seed(settings.input_dir, sample_complaint_text, count=5)

    result = run_batch(client=mock_client, settings=settings, limit=2)

    assert len(result.records) == 2


def test_final_report_has_one_row_per_document(settings, mock_client, sample_complaint_text):
    _seed(settings.input_dir, sample_complaint_text, count=3)
    result = run_batch(client=mock_client, settings=settings)

    path = write_final_report(result, settings)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))

    assert len(rows) == 3
    assert list(rows[0].keys()) == REPORT_COLUMNS
    assert rows[0]["complaint_category"] == "Billing"
    assert rows[0]["escalation_required"] == "No"
    assert rows[0]["email_generated"] == "Yes"


def test_failed_document_still_appears_in_the_report(
    settings, mock_client, sample_complaint_text
):
    """A file that could not be processed must be visible, not silently missing."""
    _seed(settings.input_dir, sample_complaint_text, count=1)
    (settings.input_dir / "broken.txt").write_text("", encoding="utf-8")

    result = run_batch(client=mock_client, settings=settings)
    rows = list(csv.DictReader(write_final_report(result, settings).open(encoding="utf-8")))

    failed = next(row for row in rows if row["case_id"] == "broken")
    assert failed["processing_status"] == "FAILED"
    assert failed["errors"]
    assert failed["complaint_category"] == ""


def test_run_manifest_records_the_run(settings, mock_client, sample_complaint_text):
    _seed(settings.input_dir, sample_complaint_text, count=2)
    result = run_batch(client=mock_client, settings=settings)

    manifest = json.loads(write_run_manifest(result, settings).read_text(encoding="utf-8"))

    assert manifest["provider"] == "mock"
    assert manifest["documents_processed"] == 2
    assert manifest["succeeded"] == 2
    assert manifest["task_mode"] == settings.task_mode.value


def test_rerunning_overwrites_rather_than_duplicates(
    settings, mock_client, sample_complaint_text
):
    """Case ids are deterministic, so a second run must be idempotent."""
    _seed(settings.input_dir, sample_complaint_text, count=2)

    run_batch(client=mock_client, settings=settings)
    run_batch(client=mock_client, settings=settings)

    assert len(list(settings.structured_data_dir.glob("*.json"))) == 2
