"""The LLM interface the rest of the application programs against.

Every task module depends only on `LLMClient`, never on a vendor SDK. That is
what makes the provider swappable at runtime (`--provider openai|gemini|mock`)
and what makes the tasks unit-testable without network access.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from complaint_processor.logging_setup import get_logger

logger = get_logger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class UsageStats(BaseModel):
    """Cumulative token/call accounting for one run."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient(ABC):
    """A provider that can return a validated instance of a Pydantic schema."""

    #: Human-readable provider name, used in logs and the run summary.
    provider_name: str = "base"

    def __init__(self, model: str, temperature: float) -> None:
        self.model = model
        self.temperature = temperature
        self.usage = UsageStats()
        # Batch processing calls this from several threads at once.
        self._usage_lock = threading.Lock()

    @abstractmethod
    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        task_name: str,
    ) -> SchemaT:
        """Return an instance of `schema` populated by the model.

        Implementations must raise `LLMCallError` when the provider itself fails
        and `LLMResponseError` when the payload cannot be validated against
        `schema`, so callers can tell a transport problem from a data problem.
        """

    def _record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        with self._usage_lock:
            self.usage.calls += 1
            self.usage.prompt_tokens += prompt_tokens
            self.usage.completion_tokens += completion_tokens

    def describe(self) -> str:
        return f"{self.provider_name}:{self.model}"
