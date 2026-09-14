"""Section-aware chunking for the policy markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SECTION_HEADER = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PolicyChunk:
    """One retrievable unit of the policy document.

    ``section_id`` is the markdown heading verbatim. It is what the model is
    told to cite and what the API returns in ``sources``, so citations stay
    traceable to a real heading rather than a chunk index.
    """

    section_id: str
    text: str
    document: str

    @property
    def citation(self) -> str:
        return f"{self.document} § {self.section_id}"

    @property
    def embedding_text(self) -> str:
        return f"{self.section_id}\n{self.text}"


def chunk_policy_markdown(markdown: str, document: str) -> list[PolicyChunk]:
    """Split a policy document into one chunk per ``##`` section.

    The documents in scope are short and already structured by heading, so a
    heading-aligned split beats a fixed-size window: it keeps each coverage
    rule intact and gives every chunk a human-meaningful citation label.
    """
    matches = list(SECTION_HEADER.finditer(markdown))
    chunks: list[PolicyChunk] = []

    for position, match in enumerate(matches):
        start = match.end()
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        if body:
            chunks.append(
                PolicyChunk(
                    section_id=match.group("title").strip(),
                    text=body,
                    document=document,
                )
            )

    if not chunks:
        preamble = markdown.strip()
        if preamble:
            chunks.append(
                PolicyChunk(section_id="Document", text=preamble, document=document)
            )
    return chunks


def load_policy_chunks(path: Path) -> list[PolicyChunk]:
    if not path.exists():
        raise FileNotFoundError(f"Policy document not found at {path}")
    return chunk_policy_markdown(path.read_text(encoding="utf-8"), path.name)
