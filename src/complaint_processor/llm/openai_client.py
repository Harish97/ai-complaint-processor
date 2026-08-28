"""OpenAI provider.

Uses the SDK's native structured-output parsing (`chat.completions.parse`),
which sends the Pydantic model as a strict JSON schema and returns a validated
instance. That removes the whole class of "the model wrapped its JSON in
markdown fences" bugs that manual parsing has to defend against.
"""

from __future__ import annotations

import time

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from complaint_processor.exceptions import LLMCallError, LLMResponseError
from complaint_processor.llm.base import LLMClient, SchemaT
from complaint_processor.logging_setup import get_logger

logger = get_logger(__name__)


class OpenAIClient(LLMClient):
    """Structured generation backed by the OpenAI Chat Completions API."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        super().__init__(model=model, temperature=temperature)

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment problem
            raise LLMCallError(
                "The `openai` package is not installed; run `pip install -r requirements.txt`"
            ) from exc

        # `max_retries=0`: retries are handled by tenacity below so that the
        # backoff policy is identical across every provider.
        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        self._max_retries = max_retries

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        task_name: str,
    ) -> SchemaT:
        from openai import APIError, APITimeoutError, RateLimitError

        retryable = (APITimeoutError, RateLimitError, APIError)

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=20),
            retry=retry_if_exception_type(retryable),
            reraise=True,
        )
        def _call():
            return self._client.chat.completions.parse(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=schema,
            )

        started = time.perf_counter()
        try:
            completion = _call()
        except Exception as exc:  # noqa: BLE001 - normalised into our own error type
            raise LLMCallError(
                f"OpenAI call failed for task '{task_name}' after "
                f"{self._max_retries} attempt(s): {exc}"
            ) from exc

        elapsed = time.perf_counter() - started

        if completion.usage is not None:
            self._record_usage(
                completion.usage.prompt_tokens,
                completion.usage.completion_tokens,
            )

        message = completion.choices[0].message

        if getattr(message, "refusal", None):
            raise LLMResponseError(
                f"Model refused task '{task_name}': {message.refusal}"
            )

        parsed = message.parsed
        if parsed is None:
            raise LLMResponseError(
                f"OpenAI returned no parsable object for task '{task_name}' "
                f"(finish_reason={completion.choices[0].finish_reason})"
            )

        logger.debug(
            "openai/%s completed task '%s' in %.2fs", self.model, task_name, elapsed
        )
        return parsed
