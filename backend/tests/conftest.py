"""Shared fixtures.

The suite runs entirely offline: no LLM key, no embedding download, no
network. The model is a scripted stub and retrieval uses the lexical backend,
so tool wiring, citation harvesting and the guard can all be asserted
deterministically.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterator, Sequence

import pytest
from fastapi.testclient import TestClient
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.config import Settings
from app.main import create_app

def _fixture_dir() -> Path:
    """Locate the fixture data, running from a checkout or from the image.

    In a checkout the data lives at <repo>/data. In the container the backend
    is copied to /srv and the same files arrive via the /data volume mount.
    """
    candidates = [
        Path(__file__).resolve().parents[2] / "data",  # repo checkout
        Path(os.getenv("DATA_DIR", "/data")),          # container
    ]
    for candidate in candidates:
        if (candidate / "sample_policy.md").exists():
            return candidate
    raise RuntimeError(
        "Could not locate fixture data. Looked in: "
        + ", ".join(str(c) for c in candidates)
    )


FIXTURE_DIR = _fixture_dir()


class ScriptedChatModel(BaseChatModel):
    """A chat model that replays a fixed list of AI messages in order.

    ``bind_tools`` is a no-op: the script already encodes which tool calls the
    model would have made, which is exactly what these tests need to assert
    about the graph's behaviour around the model.
    """

    responses: list[AIMessage] = []
    calls: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError("ScriptedChatModel ran out of scripted responses.")
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the fixture data, isolated per test."""
    target = tmp_path / "data"
    target.mkdir()
    shutil.copy(FIXTURE_DIR / "sample_policy.md", target / "sample_policy.md")
    shutil.copy(FIXTURE_DIR / "mock_claims.json", target / "mock_claims.json")
    return target


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        data_dir=data_dir,
        rag_backend="keyword",
        llm_provider="groq",
        groq_api_key="test-key-unused",
    )


@pytest.fixture
def make_client(settings: Settings):
    """Build a TestClient whose agent replays the given scripted responses."""

    def _factory(responses: list[AIMessage]) -> Iterator[TestClient]:
        model = ScriptedChatModel(responses=list(responses), calls=[])
        app = create_app(settings=settings, model=model)
        # Exposed so tests can assert on what the model actually received.
        app.state.scripted_model = model
        return TestClient(app)

    return _factory


@pytest.fixture
def claims_on_disk(data_dir: Path):
    def _read() -> list[dict]:
        return json.loads((data_dir / "mock_claims.json").read_text())

    return _read
