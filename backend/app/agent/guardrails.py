"""Input screening for prompt-injection and malformed messages.

This is a first line of defence, not the only one. Pattern matching catches
the blunt attempts; the second line is in the system prompt, which instructs
the model to treat retrieved policy text and tool output as data rather than
as instructions, and the third is that the tools validate their own arguments
so a jailbroken turn still cannot write an invalid claim.

Patterns are written to require an instruction-shaped object ("ignore your
instructions"), not a bare verb, because a policyholder legitimately writes
things like "the contractor ignored the leak".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}?"
            r"\b(above|previous|prior|earlier|initial|all|any|your|the)\b"
            r"[^.\n]{0,20}?\b(instruction|instructions|prompt|prompts|rule|rules|"
            r"direction|directions|guideline|guidelines|constraint|constraints)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_extraction",
        re.compile(
            r"\b(reveal|show|print|repeat|output|display|disclose|tell me)\b"
            r"[^.\n]{0,40}?\b(system prompt|system message|your prompt|your "
            r"instructions|initial prompt|hidden prompt)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "persona_override",
        re.compile(
            r"\b(you are now|from now on you|act as if you|pretend (that )?you|"
            r"developer mode|dan mode|jailbreak|no longer bound|without any "
            r"restrictions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_marker_injection",
        re.compile(
            r"(<\|im_(start|end)\|>|\[/?INST\]|<<SYS>>|^\s*###\s*(system|assistant)\b)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "tool_coercion",
        re.compile(
            r"\b(approve|mark|set|change|update)\b[^.\n]{0,30}?\b(claim|claims)\b"
            r"[^.\n]{0,30}?\b(approved|paid|without|regardless|anyway|no review)\b",
            re.IGNORECASE,
        ),
    ),
]

REFUSAL_MESSAGE = (
    "I can't act on that request. I can answer questions about your OmniCare "
    "policy coverage, check the status of an existing claim, or help you file "
    "a new one."
)


@dataclass(frozen=True)
class GuardResult:
    blocked: bool
    reason: str | None = None
    message: str | None = None


def screen_message(message: str, *, max_chars: int) -> GuardResult:
    """Screen an inbound user message before it reaches the model."""
    if not message or not message.strip():
        return GuardResult(
            blocked=True,
            reason="empty_message",
            message="I didn't catch that. What can I help you with?",
        )

    if len(message) > max_chars:
        return GuardResult(
            blocked=True,
            reason="message_too_long",
            message=(
                f"That message is longer than the {max_chars} character limit. "
                "Could you shorten it?"
            ),
        )

    for reason, pattern in _INJECTION_PATTERNS:
        if pattern.search(message):
            return GuardResult(blocked=True, reason=reason, message=REFUSAL_MESSAGE)

    return GuardResult(blocked=False)
