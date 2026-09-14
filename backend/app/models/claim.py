"""Pydantic models for claim data and tool inputs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

POLICY_NUMBER_PATTERN = r"^POL-\d{4}$"
CLAIM_ID_PATTERN = r"^CLM-\d{4}$"


class ClaimType(str, Enum):
    """Claim categories the assistant is allowed to file.

    Deliberately closed: the two categories the policy document actually
    covers, plus an escape hatch that routes to manual review.
    """

    WATER_DAMAGE = "Water Damage"
    PERSONAL_PROPERTY = "Personal Property"
    OTHER = "Other"


class ClaimStatus(str, Enum):
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    DENIED = "Denied"


class SubmitClaimInput(BaseModel):
    """Validated arguments for ``submit_claim``.

    This is the schema handed to the model, so the field descriptions double
    as the tool's argument documentation.
    """

    model_config = {"extra": "forbid"}

    policy_number: Annotated[
        str,
        Field(
            pattern=POLICY_NUMBER_PATTERN,
            description="Policyholder's policy number, formatted POL-1234.",
        ),
    ]
    claim_type: Annotated[
        ClaimType,
        Field(description="One of: Water Damage, Personal Property, Other."),
    ]
    amount: Annotated[
        float,
        Field(
            gt=0,
            le=1_000_000,
            description="Claimed amount in USD, greater than 0.",
        ),
    ]
    description: Annotated[
        str,
        Field(
            min_length=10,
            max_length=1000,
            description="What happened, in the policyholder's own words.",
        ),
    ]

    @field_validator("policy_number", mode="before")
    @classmethod
    def _normalise_policy_number(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise ValueError("description must be at least 10 characters")
        return stripped


class ClaimLookupInput(BaseModel):
    """Validated arguments for ``get_claim_status``."""

    model_config = {"extra": "forbid"}

    claim_id: Annotated[
        str,
        Field(
            pattern=CLAIM_ID_PATTERN,
            description="Claim reference, formatted CLM-1234.",
        ),
    ]

    @field_validator("claim_id", mode="before")
    @classmethod
    def _normalise_claim_id(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PolicySearchInput(BaseModel):
    """Validated arguments for ``search_policy``."""

    model_config = {"extra": "forbid"}

    query: Annotated[
        str,
        Field(
            min_length=3,
            max_length=500,
            description="Coverage question to look up in the policy document.",
        ),
    ]


class Claim(BaseModel):
    """A claim record as persisted in the claims store.

    ``claim_id``, ``policy_number``, ``claim_type``, ``status`` and ``amount``
    match the shape of the provided fixture exactly; ``description`` and
    ``submitted_at`` are additive and only present on records this service
    created.
    """

    claim_id: str = Field(pattern=CLAIM_ID_PATTERN)
    policy_number: str = Field(pattern=POLICY_NUMBER_PATTERN)
    claim_type: str
    status: ClaimStatus = ClaimStatus.SUBMITTED
    amount: float = Field(gt=0)
    description: str | None = None
    submitted_at: str | None = None

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
