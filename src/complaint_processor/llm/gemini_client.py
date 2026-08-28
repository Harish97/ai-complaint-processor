"""Google Gemini provider.

Gemini supports constrained decoding by passing a Pydantic model as
`response_schema`; the SDK then exposes the validated object on
`response.parsed`. Behaviourally equivalent to the OpenAI client, so the two are
interchangeable behind `LLMClient`.
"""

from __future__ import annotations

import time

from tenacity import retry, stop_after_attempt, wait_exponential

from complaint_processor.exceptions import LLMCallError, LLMResponseError
from complaint_processor.llm.base import LLMClient, SchemaT
from complaint_processor.logging_setup import get_logger

logger = get_logger(__name__)


class GeminiClient(LLMClient):
    """Structured generation backed by the Google Gemini API."""

    provider_name = "gemini"

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
            from google import genai
        except ImportError as exc:  # pragma: no cover - environment problem
            raise LLMCallError(
                "The `google-genai` package is not installed; "
                "run `pip install -r requirements.txt`"
            ) from exc

        self._genai = genai
        self._client = genai.Client(
            api_key=api_key,
            http_options={"timeout": int(timeout_seconds * 1000)},  # milliseconds
        )
        self._max_retries = max_retries

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        task_name: str,
    ) -> SchemaT:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self.temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=20),
            reraise=True,
        )
        def _call():
            return self._client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=config,
            )

        started = time.perf_counter()
        try:
            response = _call()
        except Exception as exc:  # noqa: BLE001 - normalised into our own error type
            raise LLMCallError(
                f"Gemini call failed for task '{task_name}' after "
                f"{self._max_retries} attempt(s): {exc}"
            ) from exc

        elapsed = time.perf_counter() - started

        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            self._record_usage(
                getattr(usage, "prompt_token_count", 0) or 0,
                getattr(usage, "candidates_token_count", 0) or 0,
            )

        parsed = getattr(response, "parsed", None)
        if parsed is None:
            raise LLMResponseError(
                f"Gemini returned no parsable object for task '{task_name}'. "
                f"Raw text: {(getattr(response, 'text', '') or '')[:300]}"
            )
        if not isinstance(parsed, schema):
            # Defensive: the SDK occasionally hands back a plain dict.
            try:
                parsed = schema.model_validate(parsed)
            except Exception as exc:  # noqa: BLE001
                raise LLMResponseError(
                    f"Gemini payload did not match schema for task '{task_name}': {exc}"
                ) from exc

        logger.debug(
            "gemini/%s completed task '%s' in %.2fs", self.model, task_name, elapsed
        )
        return parsed
