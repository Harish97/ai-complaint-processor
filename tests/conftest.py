"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `src/` importable without requiring an editable install.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from complaint_processor.config import LLMProvider, Settings, TaskMode  # noqa: E402
from complaint_processor.llm.mock_client import MockClient  # noqa: E402

SAMPLE_COMPLAINT = """\
CUSTOMER COMPLAINT RECORD
=========================

Reference: CMP-2025-9001
Customer Name: Priya Sharma
Email: priya.sharma@example.com
Phone: +91 98765 43210
Product / Service: Prime Home Broadband

Complaint Description:
I was billed twice for the month of February. Two charges of Rs. 1,499 were
taken from my account. I have attached copies of both invoices.

Issue Details:
Duplicate charge confirmed by the billing team.

Resolution Provided:
A refund of Rs. 1,499 was approved and processed to the original payment method.

Escalation:
Not required. Resolved at first line.

Supporting Information:
Invoice INV-20250203 and a bank statement extract.
"""


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at a temporary input/output tree."""
    input_dir = tmp_path / "data"
    input_dir.mkdir()
    return Settings(
        llm_provider=LLMProvider.MOCK,
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        batch_workers=2,
        task_mode=TaskMode.PARALLEL,
        log_level="ERROR",
    )


@pytest.fixture
def mock_client() -> MockClient:
    return MockClient()


@pytest.fixture
def sample_complaint_text() -> str:
    return SAMPLE_COMPLAINT
