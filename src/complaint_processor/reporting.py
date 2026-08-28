"""Consolidated reporting: the final CSV and the end-of-run console summary."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from complaint_processor.config import Settings
from complaint_processor.llm.base import LLMClient
from complaint_processor.logging_setup import get_logger
from complaint_processor.models import BatchResult, CaseRecord, ProcessingStatus

logger = get_logger(__name__)

REPORT_COLUMNS = [
    "case_id",
    "source_file",
    "file_type",
    "processing_status",
    "customer_name",
    "email",
    "phone_number",
    "product_or_service",
    "complaint_category",
    "is_complaint",
    "escalation_required",
    "supporting_document_available",
    "overall_case_status",
    "priority",
    "customer_sentiment",
    "resolution_provided",
    "issue_description",
    "recommended_next_action",
    "email_generated",
    "summary_generated",
    "processing_seconds",
    "errors",
]


def _yes_no(value: bool | None) -> str:
    if value is None:
        return ""
    return "Yes" if value else "No"


def _row_for(record: CaseRecord) -> dict[str, object]:
    extraction = record.extraction
    return {
        "case_id": record.meta.case_id,
        "source_file": record.meta.source_file,
        "file_type": record.meta.file_type,
        "processing_status": record.status.value,
        "customer_name": extraction.customer_name if extraction else "",
        "email": extraction.email if extraction else "",
        "phone_number": extraction.phone_number if extraction else "",
        "product_or_service": extraction.product_or_service if extraction else "",
        "complaint_category": extraction.complaint_category.value if extraction else "",
        "is_complaint": _yes_no(extraction.is_complaint if extraction else None),
        "escalation_required": _yes_no(
            extraction.escalation_required if extraction else None
        ),
        "supporting_document_available": _yes_no(
            extraction.supporting_document_available if extraction else None
        ),
        "overall_case_status": extraction.overall_case_status.value if extraction else "",
        "priority": extraction.priority.value if extraction else "",
        "customer_sentiment": extraction.customer_sentiment.value if extraction else "",
        "resolution_provided": (extraction.resolution_provided or "") if extraction else "",
        "issue_description": extraction.issue_description if extraction else "",
        "recommended_next_action": (
            record.case_summary.recommended_next_action if record.case_summary else ""
        ),
        "email_generated": _yes_no(record.customer_email is not None),
        "summary_generated": _yes_no(record.case_summary is not None),
        "processing_seconds": record.total_duration_seconds,
        "errors": " | ".join(record.errors),
    }


def write_final_report(result: BatchResult, settings: Settings) -> Path:
    """Write `output/final_report.csv` — one row per processed document."""
    path = settings.report_path
    path.parent.mkdir(parents=True, exist_ok=True)

    # newline="" is required by the csv module to avoid blank rows on Windows.
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        for record in result.records:
            writer.writerow(_row_for(record))

    logger.info("Wrote consolidated report: %s (%d rows)", path, len(result.records))
    return path


def write_run_manifest(result: BatchResult, settings: Settings) -> Path:
    """Write a machine-readable manifest of the run alongside the CSV."""
    path = settings.output_dir / "run_manifest.json"
    manifest = {
        "provider": result.provider,
        "model": result.model,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "wall_clock_seconds": result.wall_clock_seconds,
        "task_mode": settings.task_mode.value,
        "batch_workers": settings.batch_workers,
        "documents_processed": len(result.records),
        "succeeded": result.count(ProcessingStatus.SUCCESS),
        "partial": result.count(ProcessingStatus.PARTIAL),
        "failed": result.count(ProcessingStatus.FAILED),
        "skipped_files": result.skipped_files,
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def print_summary(result: BatchResult, settings: Settings, client: LLMClient) -> None:
    """Print the end-of-run summary table to the console."""
    console = Console()

    table = Table(title="Batch Processing Results", header_style="bold")
    table.add_column("Case ID", overflow="fold")
    table.add_column("Type", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Category")
    table.add_column("Priority", justify="center")
    table.add_column("Esc.", justify="center")
    table.add_column("Time (s)", justify="right")

    status_styles = {
        ProcessingStatus.SUCCESS: "green",
        ProcessingStatus.PARTIAL: "yellow",
        ProcessingStatus.FAILED: "red",
    }

    for record in result.records:
        extraction = record.extraction
        style = status_styles[record.status]
        table.add_row(
            record.meta.case_id,
            record.meta.file_type,
            f"[{style}]{record.status.value}[/{style}]",
            extraction.complaint_category.value if extraction else "—",
            extraction.priority.value if extraction else "—",
            _yes_no(extraction.escalation_required) if extraction else "—",
            f"{record.total_duration_seconds:.2f}",
        )

    console.print()
    console.print(table)

    succeeded = result.count(ProcessingStatus.SUCCESS)
    partial = result.count(ProcessingStatus.PARTIAL)
    failed = result.count(ProcessingStatus.FAILED)

    console.print(
        f"\n[bold]Provider:[/bold] {result.provider} ([dim]{result.model}[/dim])   "
        f"[bold]Task mode:[/bold] {settings.task_mode.value}   "
        f"[bold]Workers:[/bold] {settings.batch_workers}"
    )
    console.print(
        f"[bold]Documents:[/bold] {len(result.records)}   "
        f"[green]{succeeded} succeeded[/green]   "
        f"[yellow]{partial} partial[/yellow]   "
        f"[red]{failed} failed[/red]   "
        f"[bold]Wall clock:[/bold] {result.wall_clock_seconds:.2f}s"
    )
    console.print(
        f"[bold]LLM calls:[/bold] {client.usage.calls}   "
        f"[bold]Tokens:[/bold] {client.usage.total_tokens:,} "
        f"([dim]{client.usage.prompt_tokens:,} in / "
        f"{client.usage.completion_tokens:,} out[/dim])"
    )

    if result.skipped_files:
        console.print(
            f"[yellow]Skipped (unsupported format):[/yellow] "
            f"{', '.join(result.skipped_files)}"
        )

    for record in result.records:
        for error in record.errors:
            console.print(f"  [red]•[/red] [bold]{record.meta.case_id}[/bold]: {error}")

    console.print(f"\n[bold]Output written to:[/bold] {settings.output_dir}")
