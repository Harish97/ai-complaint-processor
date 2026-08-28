"""Tests for per-document orchestration, including the failure policy.

A fake `LLMClient` is used so failure modes can be triggered deterministically —
this is exactly what the provider abstraction buys.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from complaint_processor.config import TaskMode
from complaint_processor.exceptions import LLMCallError
from complaint_processor.ingestion import LoadedDocument
from complaint_processor.llm.base import LLMClient, SchemaT
from complaint_processor.llm.mock_client import MockClient
from complaint_processor.models import (
    CaseSummary,
    CustomerEmail,
    ExtractedComplaint,
    ProcessingStatus,
)
from complaint_processor.workflow import build_case_id, process_document


class FailingClient(LLMClient):
    """An `LLMClient` that fails for a chosen set of schemas."""

    provider_name = "failing"

    def __init__(self, fail_on: tuple[type, ...]) -> None:
        super().__init__(model="test", temperature=0.0)
        self._fail_on = fail_on
        self._delegate = MockClient()

    def generate_structured(self, *, system_prompt, user_prompt, schema, task_name) -> SchemaT:
        if schema in self._fail_on:
            raise LLMCallError(f"simulated provider outage for {task_name}")
        return self._delegate.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
            task_name=task_name,
        )


@pytest.fixture
def document(tmp_path: Path, sample_complaint_text: str) -> LoadedDocument:
    path = tmp_path / "complaint_001.txt"
    path.write_text(sample_complaint_text, encoding="utf-8")
    return LoadedDocument(
        path=path,
        text=sample_complaint_text,
        file_type="txt",
        file_size_bytes=path.stat().st_size,
    )


# --- Happy path --------------------------------------------------------------


def test_all_three_tasks_produce_output(document, mock_client, settings):
    record = process_document(client=mock_client, document=document, settings=settings)

    assert record.status is ProcessingStatus.SUCCESS
    assert isinstance(record.extraction, ExtractedComplaint)
    assert isinstance(record.customer_email, CustomerEmail)
    assert isinstance(record.case_summary, CaseSummary)
    assert record.errors == []


def test_extraction_is_grounded_in_the_document(document, mock_client, settings):
    record = process_document(client=mock_client, document=document, settings=settings)

    assert record.extraction.customer_name == "Priya Sharma"
    assert record.extraction.email == "priya.sharma@example.com"
    assert record.extraction.supporting_document_available is True
    # "Escalation: Not required." must not be read as "escalation required".
    assert record.extraction.escalation_required is False


def test_sequential_and_parallel_modes_agree(document, mock_client, settings):
    """Task mode is a performance choice; it must not change the result."""
    settings.task_mode = TaskMode.PARALLEL
    parallel = process_document(client=mock_client, document=document, settings=settings)

    settings.task_mode = TaskMode.SEQUENTIAL
    sequential = process_document(client=mock_client, document=document, settings=settings)

    assert parallel.extraction == sequential.extraction
    assert parallel.customer_email == sequential.customer_email
    assert parallel.case_summary == sequential.case_summary


def test_timings_are_recorded(document, mock_client, settings):
    record = process_document(client=mock_client, document=document, settings=settings)

    assert "extraction" in record.task_durations_seconds
    assert record.total_duration_seconds >= 0


# --- Failure policy ----------------------------------------------------------


def test_extraction_failure_marks_record_failed_and_skips_downstream(document, settings):
    client = FailingClient(fail_on=(ExtractedComplaint,))

    record = process_document(client=client, document=document, settings=settings)

    assert record.status is ProcessingStatus.FAILED
    assert record.extraction is None
    # Downstream tasks depend on extraction, so they must not have been attempted.
    assert record.customer_email is None
    assert record.case_summary is None
    assert any("extraction" in error for error in record.errors)


@pytest.mark.parametrize("mode", [TaskMode.PARALLEL, TaskMode.SEQUENTIAL])
def test_downstream_failure_is_partial_not_total(document, settings, mode):
    """A failed email must not throw away a good extraction and summary."""
    settings.task_mode = mode
    client = FailingClient(fail_on=(CustomerEmail,))

    record = process_document(client=client, document=document, settings=settings)

    assert record.status is ProcessingStatus.PARTIAL
    assert record.extraction is not None
    assert record.customer_email is None
    assert record.case_summary is not None
    assert any("customer_email" in error for error in record.errors)


def test_both_downstream_failures_still_keep_the_extraction(document, settings):
    client = FailingClient(fail_on=(CustomerEmail, CaseSummary))

    record = process_document(client=client, document=document, settings=settings)

    assert record.status is ProcessingStatus.PARTIAL
    assert record.extraction is not None
    assert len(record.errors) == 2


def test_workflow_never_raises_on_a_broken_provider(document, settings):
    """A batch must survive any single document, whatever the provider does."""

    class ExplodingClient(LLMClient):
        provider_name = "exploding"

        def generate_structured(self, **_):
            raise RuntimeError("totally unexpected")

    record = process_document(
        client=ExplodingClient(model="x", temperature=0), document=document, settings=settings
    )

    assert record.status is ProcessingStatus.FAILED
    assert record.errors


# --- Truncation and ids ------------------------------------------------------


def test_long_documents_are_truncated_and_flagged(tmp_path, mock_client, settings):
    settings.max_document_chars = 200
    long_text = "Complaint Description:\n" + ("the parcel never arrived. " * 200)
    path = tmp_path / "long.txt"
    path.write_text(long_text, encoding="utf-8")

    record = process_document(
        client=mock_client,
        document=LoadedDocument(
            path=path, text=long_text, file_type="txt", file_size_bytes=len(long_text)
        ),
        settings=settings,
    )

    assert record.meta.truncated is True
    assert record.meta.char_count == len(long_text)  # provenance keeps the true size


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("complaint_001.txt", "complaint_001"),
        ("case 12 (final).pdf", "case_12__final"),  # trailing separators trimmed
        ("weird/name.docx", "weird_name"),
    ],
)
def test_case_ids_are_stable_and_filesystem_safe(filename: str, expected: str):
    assert build_case_id(filename) == expected
