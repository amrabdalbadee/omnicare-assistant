"""Process-wide handles to the stateful resources the tools depend on.

LangChain tools are plain module-level functions, so they cannot take the
claims repository or the policy index as constructor arguments. This module
is the single, explicit seam where those dependencies are injected --
``create_app`` sets the runtime at startup and the test suite swaps in its
own instance pointing at a temporary directory.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.index import PolicyIndex
from app.tools.claims_repo import ClaimsRepository


@dataclass(frozen=True)
class Runtime:
    claims: ClaimsRepository
    policy: PolicyIndex


_runtime: Runtime | None = None


def set_runtime(runtime: Runtime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError(
            "Runtime is not configured. Build the app via create_app() before "
            "invoking tools."
        )
    return _runtime
