"""Application settings, loaded from the environment."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Every value can be overridden with an environment variable of the same
    name (case-insensitive), which is how docker-compose injects them.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- data locations ---------------------------------------------------
    data_dir: Path = Path("/data")
    policy_filename: str = "sample_policy.md"
    claims_filename: str = "mock_claims.json"

    # --- retrieval --------------------------------------------------------
    rag_backend: str = "chroma"  # "chroma" | "keyword"
    rag_top_k: int = 2

    # --- llm --------------------------------------------------------------
    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    llm_temperature: float = 0.0
    groq_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- guardrails / limits ---------------------------------------------
    max_message_chars: int = 2000
    agent_recursion_limit: int = 8

    @property
    def policy_path(self) -> Path:
        return self.data_dir / self.policy_filename

    @property
    def claims_path(self) -> Path:
        return self.data_dir / self.claims_filename

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / ".chroma"
