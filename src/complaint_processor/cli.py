"""Command-line interface.

Every flag maps onto a `Settings` field, so the CLI is a thin override layer over
configuration rather than a second source of truth.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from complaint_processor import __version__
from complaint_processor.batch import run_batch
from complaint_processor.config import LLMProvider, TaskMode, load_settings
from complaint_processor.exceptions import ComplaintProcessorError, ConfigurationError
from complaint_processor.ingestion import supported_extensions
from complaint_processor.llm import build_llm_client
from complaint_processor.logging_setup import configure_logging, get_logger
from complaint_processor.models import ProcessingStatus
from complaint_processor.reporting import (
    print_summary,
    write_final_report,
    write_run_manifest,
)

logger = get_logger(__name__)

# Exit codes, so the tool composes properly in a shell pipeline or CI job.
EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_CONFIG_ERROR = 2
EXIT_FATAL = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="complaint-processor",
        description=(
            "AI Customer Complaint & Case Processing System — batch GenAI workflow "
            "for structured extraction, customer response emails and internal "
            "case summaries."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python run.py                          # process ./data with the configured provider\n"
            "  python run.py --provider mock          # offline demo, no API key needed\n"
            "  python run.py --provider gemini        # use Gemini instead of OpenAI\n"
            "  python run.py --task-mode sequential   # disable intra-document parallelism\n"
            "  python run.py --limit 2 --log-level DEBUG\n"
            f"\nsupported input formats: {', '.join(supported_extensions())}\n"
        ),
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    io_group = parser.add_argument_group("input / output")
    io_group.add_argument(
        "--input-dir", type=Path, help="Folder to read documents from (default: ./data)"
    )
    io_group.add_argument(
        "--output-dir", type=Path, help="Folder to write results to (default: ./output)"
    )
    io_group.add_argument(
        "--limit", type=int, help="Process at most N documents (useful for a quick demo)"
    )

    llm_group = parser.add_argument_group("model")
    llm_group.add_argument(
        "--provider",
        dest="llm_provider",
        type=LLMProvider,
        choices=list(LLMProvider),
        # argparse renders enum *members* by default ("LLMProvider.OPENAI"),
        # so spell out the accepted values explicitly.
        metavar="{openai,gemini,mock}",
        help="LLM backend. 'mock' runs fully offline with no API key.",
    )
    llm_group.add_argument("--model", dest="model_override", help="Override the model name")
    llm_group.add_argument(
        "--temperature", dest="llm_temperature", type=float, help="Sampling temperature"
    )

    workflow_group = parser.add_argument_group("workflow")
    workflow_group.add_argument(
        "--task-mode",
        type=TaskMode,
        choices=list(TaskMode),
        metavar="{sequential,parallel}",
        help="Run the email and summary tasks in parallel (default) or sequentially",
    )
    workflow_group.add_argument(
        "--workers", dest="batch_workers", type=int, help="Documents to process concurrently"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log verbosity (the log file always records DEBUG)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = load_settings(
            llm_provider=args.llm_provider,
            llm_temperature=args.llm_temperature,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            batch_workers=args.batch_workers,
            task_mode=args.task_mode,
            log_level=args.log_level,
        )
    except Exception as exc:  # noqa: BLE001 - configuration is validated by pydantic
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    # --model applies to whichever provider is active.
    if args.model_override:
        if settings.llm_provider is LLMProvider.OPENAI:
            settings.openai_model = args.model_override
        elif settings.llm_provider is LLMProvider.GEMINI:
            settings.gemini_model = args.model_override

    settings.ensure_output_dirs()
    configure_logging(settings.log_level, settings.logs_dir)

    logger.info(
        "complaint-processor %s | provider=%s model=%s",
        __version__,
        settings.llm_provider.value,
        settings.model_name_for_active_provider(),
    )

    try:
        client = build_llm_client(settings)
    except ConfigurationError as exc:
        logger.error("%s", exc)
        return EXIT_CONFIG_ERROR

    try:
        result = run_batch(client=client, settings=settings, limit=args.limit)
    except ComplaintProcessorError as exc:
        logger.error("Batch aborted: %s", exc)
        return EXIT_FATAL
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return EXIT_FATAL

    write_final_report(result, settings)
    write_run_manifest(result, settings)
    print_summary(result, settings, client)

    # A partial or failed document is a non-zero exit, so automation notices.
    if result.count(ProcessingStatus.SUCCESS) != len(result.records):
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
