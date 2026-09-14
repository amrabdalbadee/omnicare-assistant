"""Retrieval tests: chunking boundaries and query routing."""

from app.rag.chunking import chunk_policy_markdown, load_policy_chunks
from app.rag.index import KeywordPolicyIndex, build_policy_index


def test_chunking_splits_on_section_headers(data_dir):
    chunks = load_policy_chunks(data_dir / "sample_policy.md")

    assert [c.section_id for c in chunks] == [
        "Section 1: Home Water Damage Coverage",
        "Section 2: Personal Property Protection",
    ]
    # The document title must not leak into a section body.
    assert "OmniCare General Insurance Policy" not in chunks[0].text
    assert chunks[0].citation == "sample_policy.md § Section 1: Home Water Damage Coverage"


def test_chunk_keeps_a_coverage_rule_intact(data_dir):
    chunks = load_policy_chunks(data_dir / "sample_policy.md")
    water = chunks[0].text

    assert "$25,000" in water and "$500 deductible" in water
    assert "strictly excluded" in water


def test_retrieval_routes_water_query_to_section_one(data_dir, settings):
    index = build_policy_index(
        data_dir / "sample_policy.md", backend="keyword", persist_dir=settings.chroma_dir
    )
    hits = index.search("is a burst pipe covered?", top_k=1)

    assert hits[0].section_id == "Section 1: Home Water Damage Coverage"


def test_retrieval_routes_property_query_to_section_two(data_dir, settings):
    index = build_policy_index(
        data_dir / "sample_policy.md", backend="keyword", persist_dir=settings.chroma_dir
    )
    hits = index.search("are my jewelry and electronics covered?", top_k=1)

    assert hits[0].section_id == "Section 2: Personal Property Protection"


def test_unmatched_query_still_returns_evidence():
    chunks = chunk_policy_markdown("## A\nalpha text\n\n## B\nbeta text\n", "doc.md")
    hits = KeywordPolicyIndex(chunks).search("zzzz nonexistent", top_k=2)

    # Returning nothing would let the model answer from memory instead.
    assert len(hits) == 2
