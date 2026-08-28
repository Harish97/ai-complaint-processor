"""Provider factory — the single place that knows about concrete LLM classes."""

from __future__ import annotations

from complaint_processor.config import LLMProvider, Settings
from complaint_processor.exceptions import ConfigurationError
from complaint_processor.llm.base import LLMClient
from complaint_processor.logging_setup import get_logger

logger = get_logger(__name__)

_ENV_VAR_FOR_PROVIDER = {
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.GEMINI: "GEMINI_API_KEY",
}


def build_llm_client(settings: Settings) -> LLMClient:
    """Instantiate the client for `settings.llm_provider`.

    Raises `ConfigurationError` with actionable guidance when a required API key
    is missing, rather than failing deep inside the first document.
    """
    provider = settings.llm_provider

    if provider is LLMProvider.MOCK:
        from complaint_processor.llm.mock_client import MockClient

        return MockClient(temperature=settings.llm_temperature)

    api_key = settings.api_key_for_active_provider()
    if not api_key:
        env_var = _ENV_VAR_FOR_PROVIDER[provider]
        raise ConfigurationError(
            f"Provider '{provider.value}' is selected but {env_var} is not set.\n"
            f"  - Set {env_var} in your .env file (copy .env.example to .env), or\n"
            f"  - Run the offline demo instead: python run.py --provider mock"
        )

    common = {
        "api_key": api_key,
        "model": settings.model_name_for_active_provider(),
        "temperature": settings.llm_temperature,
        "timeout_seconds": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
    }

    if provider is LLMProvider.OPENAI:
        from complaint_processor.llm.openai_client import OpenAIClient

        client: LLMClient = OpenAIClient(**common)
    elif provider is LLMProvider.GEMINI:
        from complaint_processor.llm.gemini_client import GeminiClient

        client = GeminiClient(**common)
    else:  # pragma: no cover - the enum is exhaustive
        raise ConfigurationError(f"Unsupported provider: {provider}")

    logger.info("LLM provider ready: %s", client.describe())
    return client
