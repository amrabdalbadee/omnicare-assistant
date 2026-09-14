"""Application factory and entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models import BaseChatModel

from app.agent.graph import build_graph
from app.agent.llm import build_chat_model
from app.api.routes import router
from app.config import Settings
from app.context import Runtime, set_runtime
from app.rag.index import build_policy_index
from app.tools.claims_repo import ClaimsRepository

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, model: BaseChatModel | None = None
) -> FastAPI:
    """Build the application.

    ``settings`` and ``model`` are injectable so the test suite can point at a
    temporary data directory and a scripted model without touching the
    environment or reaching the network.
    """
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "Starting OmniCare assistant (provider=%s, rag=%s, data=%s)",
            settings.llm_provider,
            settings.rag_backend,
            settings.data_dir,
        )
        policy_index = build_policy_index(
            settings.policy_path,
            backend=settings.rag_backend,
            persist_dir=settings.chroma_dir,
        )
        set_runtime(
            Runtime(
                claims=ClaimsRepository(settings.claims_path), policy=policy_index
            )
        )

        chat_model = model or build_chat_model(settings)
        app.state.settings = settings
        app.state.graph = build_graph(
            chat_model, max_message_chars=settings.max_message_chars
        )
        logger.info("Assistant ready.")
        yield

    app = FastAPI(
        title="OmniCare Financial — Customer Assistant",
        description=(
            "Prototype assistant that answers policy coverage questions from "
            "internal documents, looks up claim statuses, and files new claims."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # prototype only; restrict before any real deployment
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
