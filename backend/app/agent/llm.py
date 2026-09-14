"""Chat model construction for the supported providers."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app.config import Settings


class LLMConfigurationError(RuntimeError):
    """Raised when the selected provider is missing a key or its package."""


def build_chat_model(settings: Settings) -> BaseChatModel:
    provider = settings.llm_provider.lower().strip()
    common = {"model": settings.llm_model, "temperature": settings.llm_temperature}

    if provider == "groq":
        _require_key(settings.groq_api_key, "GROQ_API_KEY", provider)
        from langchain_groq import ChatGroq

        return ChatGroq(api_key=settings.groq_api_key, **common)

    if provider == "anthropic":
        _require_key(settings.anthropic_api_key, "ANTHROPIC_API_KEY", provider)
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(api_key=settings.anthropic_api_key, **common)

    if provider == "openai":
        _require_key(settings.openai_api_key, "OPENAI_API_KEY", provider)
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(api_key=settings.openai_api_key, **common)

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:  # pragma: no cover
            raise LLMConfigurationError(
                "LLM_PROVIDER=ollama requires langchain-ollama. Install it with "
                "`pip install langchain-ollama`."
            ) from exc
        return ChatOllama(base_url=settings.ollama_base_url, **common)

    raise LLMConfigurationError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
        "Expected one of: groq, anthropic, openai, ollama."
    )


def _require_key(value: str | None, env_name: str, provider: str) -> None:
    if not value:
        raise LLMConfigurationError(
            f"LLM_PROVIDER={provider} requires {env_name}. Copy .env.example to "
            f".env and set {env_name}, then restart."
        )
