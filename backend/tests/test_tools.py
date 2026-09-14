"""Tool-level tests: lookups, validation, and persistence."""

from __future__ import annotations

import json

import pytest

from app.context import Runtime, set_runtime
from app.models.claim import Claim, ClaimStatus, SubmitClaimInput
from app.rag.index import build_policy_index
from app.tools.claims_repo import ClaimsRepository
from app.tools.registry import (
    GET_CLAIM_STATUS_TOOL as get_claim_status,
    SEARCH_POLICY_TOOL as search_policy,
    SUBMIT_CLAIM_TOOL as submit_claim,
)


@pytest.fixture(autouse=True)
def runtime(data_dir, settings):
    set_runtime(
        Runtime(
            claims=ClaimsRepository(settings.claims_path),
            policy=build_policy_index(
                settings.policy_path, backend="keyword", persist_dir=settings.chroma_dir
            ),
        )
    )


# --- get_claim_status ------------------------------------------------------


def test_get_claim_status_returns_known_claim():
    payload = json.loads(get_claim_status.invoke({"claim_id": "CLM-8821"}))

    assert payload["ok"] is True
    assert payload["data"]["claim"]["status"] == "Approved"
    assert payload["data"]["claim"]["policy_number"] == "POL-1092"


def test_get_claim_status_is_case_insensitive():
    payload = json.loads(get_claim_status.invoke({"claim_id": "clm-9014"}))

    assert payload["data"]["claim"]["status"] == "Under Review"


def test_get_claim_status_reports_missing_claim_without_inventing_one():
    payload = json.loads(get_claim_status.invoke({"claim_id": "CLM-0001"}))

    assert payload["ok"] is False
    assert "CLM-0001" in payload["error"]


def test_get_claim_status_rejects_malformed_id():
    payload = json.loads(get_claim_status.invoke({"claim_id": "not-a-claim"}))

    assert payload["ok"] is False
    assert payload["detail"]["problems"][0]["field"] == "claim_id"


# --- submit_claim ----------------------------------------------------------


def test_submit_claim_persists_and_returns_confirmation(claims_on_disk):
    payload = json.loads(
        submit_claim.invoke(
            {
                "policy_number": "POL-1092",
                "claim_type": "Water Damage",
                "amount": 4200.50,
                "description": "Burst pipe under the kitchen sink flooded the floor.",
            }
        )
    )

    assert payload["ok"] is True
    confirmation = payload["data"]["confirmation_id"]
    assert confirmation.startswith("CLM-")

    records = claims_on_disk()
    assert len(records) == 3
    stored = records[-1]
    assert stored["claim_id"] == confirmation
    assert stored["status"] == ClaimStatus.SUBMITTED.value
    assert stored["amount"] == 4200.50


def test_submit_claim_preserves_existing_records(claims_on_disk):
    submit_claim.invoke(
        {
            "policy_number": "POL-3341",
            "claim_type": "Personal Property",
            "amount": 900,
            "description": "Laptop damaged when a shelf collapsed onto the desk.",
        }
    )
    ids = [record["claim_id"] for record in claims_on_disk()]

    assert ids[:2] == ["CLM-8821", "CLM-9014"]


def test_submit_claim_assigns_unique_ids(claims_on_disk):
    for _ in range(6):
        submit_claim.invoke(
            {
                "policy_number": "POL-1092",
                "claim_type": "Other",
                "amount": 100,
                "description": "Repeated submission used to check id allocation.",
            }
        )
    ids = [record["claim_id"] for record in claims_on_disk()]

    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "field, value",
    [
        ("policy_number", "1092"),
        ("amount", -50),
        ("amount", 0),
        ("claim_type", "Spontaneous Combustion"),
        ("description", "too short"),
    ],
)
def test_submit_claim_rejects_invalid_input(field, value, claims_on_disk):
    args = {
        "policy_number": "POL-1092",
        "claim_type": "Water Damage",
        "amount": 1000,
        "description": "A valid description of what happened to the property.",
    }
    args[field] = value
    payload = json.loads(submit_claim.invoke(args))

    assert payload["ok"] is False
    # A rejected claim must not reach disk.
    assert len(claims_on_disk()) == 2


def test_submit_claim_normalises_policy_number(claims_on_disk):
    submit_claim.invoke(
        {
            "policy_number": " pol-7777 ",
            "claim_type": "Other",
            "amount": 10,
            "description": "Whitespace and lowercase policy number normalisation.",
        }
    )

    assert claims_on_disk()[-1]["policy_number"] == "POL-7777"


def test_amount_must_be_numeric():
    with pytest.raises(Exception):
        SubmitClaimInput(
            policy_number="POL-1092",
            claim_type="Water Damage",
            amount="a lot",
            description="Non numeric amount should not validate.",
        )


# --- repository ------------------------------------------------------------


def test_repository_write_is_atomic_and_readable(settings):
    repo = ClaimsRepository(settings.claims_path)
    stored = repo.append(
        Claim(
            claim_id="CLM-0000",
            policy_number="POL-4242",
            claim_type="Other",
            amount=75.25,
            description="Direct repository write.",
            submitted_at=Claim.now_iso(),
        )
    )

    assert repo.get(stored.claim_id) is not None
    assert json.loads(settings.claims_path.read_text())[-1]["amount"] == 75.25


# --- search_policy ---------------------------------------------------------


def test_search_policy_returns_citable_sections():
    payload = json.loads(search_policy.invoke({"query": "water damage deductible"}))

    assert payload["ok"] is True
    top = payload["data"]["results"][0]
    assert top["section_id"] == "Section 1: Home Water Damage Coverage"
    assert "$500" in top["text"]


def test_search_policy_rejects_trivial_query():
    payload = json.loads(search_policy.invoke({"query": "a"}))

    assert payload["ok"] is False


def test_concurrent_submissions_do_not_lose_claims(settings, claims_on_disk):
    """Twelve parallel writers must produce twelve distinct records.

    Without the exclusive lock around the read-modify-write, interleaved
    writers read the same list and the last one to finish silently discards
    the others' claims.
    """
    from concurrent.futures import ThreadPoolExecutor

    repo = ClaimsRepository(settings.claims_path)

    def write(n: int) -> str:
        return repo.append(
            Claim(
                claim_id="CLM-0000",
                policy_number="POL-1092",
                claim_type="Other",
                amount=float(n + 1),
                description=f"Concurrent write number {n}.",
            )
        ).claim_id

    with ThreadPoolExecutor(max_workers=12) as pool:
        returned = list(pool.map(write, range(12)))

    records = claims_on_disk()
    assert len(records) == 14  # 2 fixtures + 12 new
    assert len(set(returned)) == 12
    assert set(returned) <= {r["claim_id"] for r in records}
