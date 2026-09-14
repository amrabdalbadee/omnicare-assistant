"""The tools exposed to the agent.

Every tool returns a JSON string with a stable shape:

    {"ok": true,  "data": {...}}
    {"ok": false, "error": "...", "detail": {...}}

Two reasons for the uniform envelope. The agent can distinguish "the tool ran
and found nothing" from "the tool rejected my arguments" and recover by asking
the user, instead of guessing. And the finalize node can parse results into
the API's ``sources`` and ``tool_calls`` fields without depending on how the
model happened to phrase its answer.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import ValidationError

from app.context import get_runtime
from app.models.claim import (
    Claim,
    ClaimLookupInput,
    ClaimStatus,
    ClaimType,
    PolicySearchInput,
    SubmitClaimInput,
)


def _ok(data: dict[str, Any]) -> str:
    return json.dumps({"ok": True, "data": data})


def _error(message: str, **detail: Any) -> str:
    return json.dumps({"ok": False, "error": message, "detail": detail})


def _validation_error(exc: ValidationError) -> str:
    problems = [
        {"field": ".".join(str(p) for p in err["loc"]), "problem": err["msg"]}
        for err in exc.errors()
    ]
    return _error(
        "Invalid arguments. Ask the policyholder for the missing or corrected "
        "values, then call the tool again.",
        problems=problems,
    )


# --- tool 0: policy retrieval ---------------------------------------------


def search_policy(query: str) -> str:
    """Search the OmniCare policy document for coverage rules.

    Use this for any question about what is covered, excluded, limited, or
    what deductibles and thresholds apply. Cite the returned section_id values
    in your answer.
    """
    try:
        args = PolicySearchInput(query=query)
    except ValidationError as exc:
        return _validation_error(exc)

    runtime = get_runtime()
    chunks = runtime.policy.search(args.query, top_k=2)
    return _ok(
        {
            "results": [
                {
                    "section_id": chunk.section_id,
                    "document": chunk.document,
                    "citation": chunk.citation,
                    "text": chunk.text,
                }
                for chunk in chunks
            ]
        }
    )


# --- tool 1: claim status --------------------------------------------------


def get_claim_status(claim_id: str) -> str:
    """Look up the current status of an existing claim by its claim id.

    Only report a status this tool actually returned. If the claim is not
    found, say so and offer to file a new claim.
    """
    try:
        args = ClaimLookupInput(claim_id=claim_id)
    except ValidationError as exc:
        return _validation_error(exc)

    record = get_runtime().claims.get(args.claim_id)
    if record is None:
        return _error(
            f"No claim found with id {args.claim_id}.", claim_id=args.claim_id
        )
    return _ok({"claim": record})


# --- tool 2: claim submission ---------------------------------------------


def submit_claim(
    policy_number: str, claim_type: ClaimType | str, amount: float, description: str
) -> str:
    """File a new insurance claim and return its confirmation id.

    Only call this once every argument has been confirmed by the policyholder.
    Never invent a policy number, an amount, or a description.
    """
    try:
        args = SubmitClaimInput(
            policy_number=policy_number,
            claim_type=claim_type,
            amount=amount,
            description=description,
        )
    except ValidationError as exc:
        return _validation_error(exc)

    claim = Claim(
        claim_id="CLM-0000",  # replaced by the repository under its lock
        policy_number=args.policy_number,
        claim_type=args.claim_type.value,
        status=ClaimStatus.SUBMITTED,
        amount=args.amount,
        description=args.description,
        submitted_at=Claim.now_iso(),
    )
    stored = get_runtime().claims.append(claim)
    return _ok(
        {
            "confirmation_id": stored.claim_id,
            "claim": stored.model_dump(exclude_none=True),
        }
    )


# `handle_validation_error` matters more than it looks. Without it, arguments
# that fail the schema raise before the function body runs, and the agent gets
# a stack trace instead of something it can act on. Routing those failures
# through the same envelope means a malformed amount comes back as "ask the
# policyholder for a corrected value" whether it was caught by the schema or
# by the function.
SEARCH_POLICY_TOOL = StructuredTool.from_function(
    func=search_policy,
    name="search_policy",
    args_schema=PolicySearchInput,
    handle_validation_error=_validation_error,
)

GET_CLAIM_STATUS_TOOL = StructuredTool.from_function(
    func=get_claim_status,
    name="get_claim_status",
    args_schema=ClaimLookupInput,
    handle_validation_error=_validation_error,
)

SUBMIT_CLAIM_TOOL = StructuredTool.from_function(
    func=submit_claim,
    name="submit_claim",
    args_schema=SubmitClaimInput,
    handle_validation_error=_validation_error,
)

TOOLS = [SEARCH_POLICY_TOOL, GET_CLAIM_STATUS_TOOL, SUBMIT_CLAIM_TOOL]
RETRIEVAL_TOOL_NAMES = {"search_policy"}
