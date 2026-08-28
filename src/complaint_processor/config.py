"""Application configuration.

All tunable values live here and are loaded from environment variables or a
`.env` file, so nothing operational is hard-coded in the business logic.
CLI flags (see `cli.py`) override these at runtime.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/complaint_processor/config.py -> src/complaint_processor -> src -> <root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LLMProvider(str, Enum):
    """Supported LLM backends."""

    OPENAI = "openai"
    GEMINI = "gemini"
    MOCK = "mock"


class TaskMode(str, Enum):
    """How the two downstream generation tasks are executed per document."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class Settings(BaseSettings):
    """Runtime settings, populated from the environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM provider selection ---
    llm_provider: LLMProvider = Field(
        default=LLMProvider.OPENAI,
        description="Which backend to use. 'mock' runs fully offline with no API key.",
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # --- LLM behaviour ---
    llm_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Low by default: extraction should be reproducible, not creative.",
    )
    llm_max_retries: int = Field(default=3, ge=1, le=10)
    llm_timeout_seconds: float = Field(default=90.0, gt=0)

    # --- Paths ---
    input_dir: Path = PROJECT_ROOT / "data"
    output_dir: Path = PROJECT_ROOT / "output"

    # --- Workflow / batch behaviour ---
    batch_workers: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Documents processed concurrently.",
    )
    task_mode: TaskMode = Field(
        default=TaskMode.PARALLEL,
        description="Whether email + summary generation run side by side.",
    )
    max_document_chars: int = Field(
        default=20_000,
        gt=0,
        description="Documents are truncated to this length to bound token cost.",
    )

    # --- Observability ---
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}, got {value!r}")
        return level

    @field_validator("input_dir", "output_dir")
    @classmethod
    def _expand_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    # --- Derived output locations ---

    @property
    def structured_data_dir(self) -> Path:
        return self.output_dir / "structured_data"

    @property
    def customer_emails_dir(self) -> Path:
        return self.output_dir / "customer_emails"

    @property
    def case_summaries_dir(self) -> Path:
        return self.output_dir / "case_summaries"

    @property
    def logs_dir(self) -> Path:
        return self.output_dir / "logs"

    @property
    def report_path(self) -> Path:
        return self.output_dir / "final_report.csv"

    def ensure_output_dirs(self) -> None:
        """Create every output directory the pipeline writes into."""
        for directory in (
            self.output_dir,
            self.structured_data_dir,
            self.customer_emails_dir,
            self.case_summaries_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def api_key_for_active_provider(self) -> str | None:
        """Return the API key belonging to the currently selected provider."""
        return {
            LLMProvider.OPENAI: self.openai_api_key,
            LLMProvider.GEMINI: self.gemini_api_key,
            LLMProvider.MOCK: "not-required",
        }[self.llm_provider]

    def model_name_for_active_provider(self) -> str:
        return {
            LLMProvider.OPENAI: self.openai_model,
            LLMProvider.GEMINI: self.gemini_model,
            LLMProvider.MOCK: "offline-rule-based",
        }[self.llm_provider]


def load_settings(**overrides: object) -> Settings:
    """Build a `Settings` instance, applying non-`None` CLI overrides on top."""
    clean = {key: value for key, value in overrides.items() if value is not None}
    return Settings(**clean)  # type: ignore[arg-type]
