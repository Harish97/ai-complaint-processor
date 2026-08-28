"""Batch orchestration: discover files, run the workflow over each, collect results.

Documents are independent of one another, so the batch is a straightforward
concurrent map with a bounded worker pool. The pool size is bounded (rather than
"one thread per file") so that a folder of 500 documents does not open 500
simultaneous connections and trip provider rate limits.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from complaint_processor.config import Settings
from complaint_processor.exceptions import IngestionError
from complaint_processor.ingestion import discover_documents, load_document
from complaint_processor.llm.base import LLMClient
from complaint_processor.logging_setup import get_logger
from complaint_processor.models import (
    BatchResult,
    CaseRecord,
    DocumentMeta,
    ProcessingStatus,
)
from complaint_processor.persistence import write_case_outputs
from complaint_processor.workflow import build_case_id, process_document

logger = get_logger(__name__)


def _failed_record(path: Path, message: str) -> CaseRecord:
    """Build a FAILED record for a file that could not even be loaded."""
    try:
        size = path.stat().st_size
    except OSError:
        size = 0

    return CaseRecord(
        meta=DocumentMeta(
            case_id=build_case_id(path.name),
            source_file=path.name,
            file_type=path.suffix.lower().lstrip("."),
            file_size_bytes=size,
            char_count=0,
        ),
        status=ProcessingStatus.FAILED,
        errors=[f"ingestion: {message}"],
    )


def _process_one(path: Path, client: LLMClient, settings: Settings) -> CaseRecord:
    """Load and process a single file, converting any failure into a record.

    This function is the unit of work submitted to the pool, so it must never
    raise — an exception escaping here would kill the future, not the batch, and
    the file would silently vanish from the report.
    """
    try:
        document = load_document(path)
    except IngestionError as exc:
        logger.error("Could not ingest %s: %s", path.name, exc)
        return _failed_record(path, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected ingestion failure for %s", path.name)
        return _failed_record(path, f"unexpected error: {exc}")

    record = process_document(client=client, document=document, settings=settings)

    try:
        write_case_outputs(record, settings)
    except OSError as exc:
        record.errors.append(f"persistence: {exc}")
        logger.error("Could not write outputs for %s: %s", record.meta.case_id, exc)

    return record


def run_batch(
    *, client: LLMClient, settings: Settings, limit: int | None = None
) -> BatchResult:
    """Process every eligible document in `settings.input_dir`."""
    settings.ensure_output_dirs()

    eligible, skipped = discover_documents(settings.input_dir)
    if limit is not None:
        eligible = eligible[:limit]
        logger.info("Limiting this run to %d document(s)", len(eligible))

    started_at = datetime.now(timezone.utc)
    records: list[CaseRecord] = []

    if not eligible:
        logger.warning(
            "No processable documents found in %s (supported: %s)",
            settings.input_dir,
            ", ".join(sorted({p.suffix for p in skipped})) or "none present",
        )
    else:
        workers = min(settings.batch_workers, len(eligible))
        logger.info(
            "Starting batch: %d document(s), %d worker(s), task mode '%s'",
            len(eligible),
            workers,
            settings.task_mode.value,
        )

        progress_columns = (
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        )

        with Progress(*progress_columns, transient=True) as progress:
            task = progress.add_task("Processing documents", total=len(eligible))

            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="doc"
            ) as pool:
                futures = {
                    pool.submit(_process_one, path, client, settings): path
                    for path in eligible
                }
                for future in as_completed(futures):
                    records.append(future.result())
                    progress.advance(task)

        # Futures complete out of order; sort so the report is stable run to run.
        records.sort(key=lambda record: record.meta.source_file)

    finished_at = datetime.now(timezone.utc)

    result = BatchResult(
        records=records,
        started_at=started_at,
        finished_at=finished_at,
        provider=client.provider_name,
        model=client.model,
        skipped_files=[path.name for path in skipped],
    )

    logger.info(
        "Batch finished in %.2fs: %d succeeded, %d partial, %d failed",
        result.wall_clock_seconds,
        result.count(ProcessingStatus.SUCCESS),
        result.count(ProcessingStatus.PARTIAL),
        result.count(ProcessingStatus.FAILED),
    )
    return result
