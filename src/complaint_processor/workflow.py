"""Per-document workflow orchestration.

The dependency graph for one document is:

        document text
              |
              v
    [1] structured extraction          (must succeed first)
              |
      +-------+-------+
      |               |
      v               v
 [2] customer     [3] internal
     email         case summary        (independent of each other)

Step 1 is a hard dependency: both downstream tasks consume its *validated*
output, so they cannot start until it lands. Steps 2 and 3 depend only on step 1
and not on each other, so they are run concurrently by default — that is the
"parallel where appropriate" part of the brief, and it roughly halves the
per-document latency. `--task-mode sequential` runs them one after another so
the two strategies can be compared during a demo.

Failure policy is graded rather than all-or-nothing:
  * extraction fails  -> the record is FAILED, downstream tasks are skipped
  * one downstream task fails -> the record is PARTIAL and everything that did
    succeed is still written to disk

Nothing here raises: a document that cannot be processed becomes a FAILED
record so that a single bad file never aborts a batch.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Callable, Iterator, TypeVar

from complaint_processor.config import Settings, TaskMode
from complaint_processor.exceptions import ComplaintProcessorError
from complaint_processor.ingestion import LoadedDocument
from complaint_processor.llm.base import LLMClient
from complaint_processor.logging_setup import get_logger
from complaint_processor.models import (
    CaseRecord,
    CaseSummary,
    CustomerEmail,
    DocumentMeta,
    ExtractedComplaint,
    ProcessingStatus,
)
from complaint_processor.tasks import (
    extract_complaint,
    generate_case_summary,
    generate_customer_email,
)

logger = get_logger(__name__)

T = TypeVar("T")


def build_case_id(source_file: str) -> str:
    """Derive a stable, filesystem-safe case id from the source file name.

    Deterministic on purpose: re-running the batch overwrites the same outputs
    instead of accumulating duplicates.
    """
    stem = source_file.rsplit(".", 1)[0]
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in stem)
    return safe.strip("_") or "case"


@contextmanager
def _timed(record: CaseRecord, key: str) -> Iterator[None]:
    """Record how long a named step took, whether or not it succeeded."""
    started = time.perf_counter()
    try:
        yield
    finally:
        record.task_durations_seconds[key] = round(time.perf_counter() - started, 3)


def _prepare_text(document: LoadedDocument, max_chars: int) -> tuple[str, bool]:
    """Truncate over-long documents so token cost stays bounded and predictable."""
    if len(document.text) <= max_chars:
        return document.text, False
    logger.warning(
        "%s is %d chars; truncating to %d for the LLM",
        document.path.name,
        len(document.text),
        max_chars,
    )
    return document.text[:max_chars], True


def process_document(
    *,
    client: LLMClient,
    document: LoadedDocument,
    settings: Settings,
) -> CaseRecord:
    """Run all three AI tasks over one document and return the case record."""
    source_file = document.path.name
    text, truncated = _prepare_text(document, settings.max_document_chars)

    meta = DocumentMeta(
        case_id=build_case_id(source_file),
        source_file=source_file,
        file_type=document.file_type,
        file_size_bytes=document.file_size_bytes,
        char_count=document.char_count,
        truncated=truncated,
    )
    record = CaseRecord(meta=meta, status=ProcessingStatus.FAILED)

    logger.info("Processing %s (case_id=%s)", source_file, meta.case_id)

    # --- Step 1: extraction (blocking dependency) ---
    try:
        with _timed(record, "extraction"):
            record.extraction = extract_complaint(
                client=client, source_file=source_file, document_text=text
            )
    except ComplaintProcessorError as exc:
        record.errors.append(f"extraction: {exc}")
        logger.error("Extraction failed for %s: %s", source_file, exc)
        return record
    except Exception as exc:  # noqa: BLE001 - a batch must survive anything
        record.errors.append(f"extraction: unexpected error: {exc}")
        logger.exception("Unexpected extraction failure for %s", source_file)
        return record

    extraction = record.extraction

    # --- Steps 2 and 3: independent of each other ---
    def run_email() -> CustomerEmail:
        return generate_customer_email(
            client=client,
            source_file=source_file,
            extraction=extraction,
            document_text=text,
        )

    def run_summary() -> CaseSummary:
        return generate_case_summary(
            client=client,
            source_file=source_file,
            extraction=extraction,
            document_text=text,
        )

    if settings.task_mode is TaskMode.PARALLEL:
        email_result, summary_result = _run_parallel(record, run_email, run_summary)
    else:
        email_result = _run_guarded(record, "customer_email", run_email)
        summary_result = _run_guarded(record, "case_summary", run_summary)

    record.customer_email = email_result
    record.case_summary = summary_result

    if email_result is not None and summary_result is not None:
        record.status = ProcessingStatus.SUCCESS
    else:
        record.status = ProcessingStatus.PARTIAL
        logger.warning(
            "%s completed partially (%d task error(s))", source_file, len(record.errors)
        )

    return record


def _run_parallel(
    record: CaseRecord,
    run_email: Callable[[], CustomerEmail],
    run_summary: Callable[[], CaseSummary],
) -> tuple[CustomerEmail | None, CaseSummary | None]:
    """Run the two downstream tasks concurrently.

    Two threads is the right primitive here: both tasks are network-bound HTTP
    calls, so they spend their time waiting on I/O with the GIL released.
    """
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="task") as pool:
        email_future = pool.submit(run_email)
        summary_future = pool.submit(run_summary)

        email = _resolve(record, "customer_email", email_future.result)
        summary = _resolve(record, "case_summary", summary_future.result)

    # Both ran at once, so attribute the wall-clock time to the pair.
    record.task_durations_seconds["downstream_tasks_parallel"] = round(
        time.perf_counter() - started, 3
    )
    return email, summary


def _run_guarded(
    record: CaseRecord, task_key: str, func: Callable[[], T]
) -> T | None:
    """Run one task sequentially, timing it and capturing any failure."""
    with _timed(record, task_key):
        return _resolve(record, task_key, func)


def _resolve(record: CaseRecord, task_key: str, func: Callable[[], T]) -> T | None:
    """Call `func`, converting any failure into a recorded error and `None`."""
    try:
        return func()
    except ComplaintProcessorError as exc:
        record.errors.append(f"{task_key}: {exc}")
        logger.error("Task '%s' failed for %s: %s", task_key, record.meta.source_file, exc)
    except Exception as exc:  # noqa: BLE001 - a batch must survive anything
        record.errors.append(f"{task_key}: unexpected error: {exc}")
        logger.exception("Unexpected failure in task '%s'", task_key)
    return None
