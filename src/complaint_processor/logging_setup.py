"""Logging configuration.

Console output goes through `rich` so a batch run is readable while it happens;
a plain-text copy of every message (including DEBUG) is written to
`output/logs/run.log` so a run can be audited afterwards.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

_CONFIGURED = False


def configure_logging(log_level: str, logs_dir: Path) -> None:
    """Attach a rich console handler and a file handler to the root logger.

    Safe to call more than once; only the first call takes effect.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # handlers decide what actually gets emitted

    console_handler = RichHandler(
        rich_tracebacks=True,
        show_path=False,
        omit_repeated_times=False,
    )
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(logging.Formatter("%(message)s", datefmt="%H:%M:%S"))

    file_handler = logging.FileHandler(logs_dir / "run.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-38s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Third-party HTTP chatter would drown out our own messages.
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Module-level logger helper, so call sites never import `logging` directly."""
    return logging.getLogger(name)
