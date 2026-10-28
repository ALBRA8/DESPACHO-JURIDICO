"""
DATA BOUNDARY — Trust-level classification + prompt-injection sanitization.

Block 2 of HARDENING-2. Establishes a hard boundary between:

- TRUSTED_CONTROL      : content the platform itself produced or controls
                         (matter_id, agent_name, system metadata). Can flow
                         directly into agent prompts.
- UNTRUSTED_CONTENT    : content retrieved from external sources that will be
                         SHOWN to the agent but never executed as instructions
                         (web pages, corpus text, LLM-generated text). Must be
                         wrapped + sanitized before reaching the agent.
- UNTRUSTED_EXTERNAL   : content whose origin is unknown. Treated as the most
                         dangerous tier — fail-closed.

The classifier is conservative: anything it cannot confidently attribute to a
control-plane source is treated as untrusted. Sanitization is layered on top of
classification, not a replacement for it.

This module is PURE PYTHON — no external deps. Regex-based detection is
intentional: we want deterministic, replayable decisions, not LLM-judged ones.
"""
from __future__ import annotations

import re
from enum import IntEnum
from typing import Any

# ---------------------------------------------------------------------------
# Trust levels
# ---------------------------------------------------------------------------


class TrustLevel(IntEnum):
    """Three-tier trust model for content entering agent prompts.

    Lower number == higher trust == fewer sanitization requirements.
    """

    TRUSTED_CONTROL = 0       # platform-generated, safe to inline
    UNTRUSTED_CONTENT = 10    # external content to display, not execute
    UNTRUSTED_EXTERNAL = 20   # unknown origin — highest caution


# ---------------------------------------------------------------------------
# Source classifier
# ---------------------------------------------------------------------------

# Sources we KNOW the platform emits itself. Matching is case-insensitive on
# the source string's leading tokens. These are control-plane identifiers that
# the harness / runtime / agents produce internally — they cannot be forged by
# document content (they come from caller-supplied `source=` metadata).
_TRUSTED_SOURCE_PREFIXES: tuple[str, ...] = (
    "matter_id:",
    "matter:",
    "agent_name:",
    "agent:",
    "system:",
    "runtime:",
    "harness:",
    "internal:",
    "platform:",
)

# Sources we KNOW come from outside the trust boundary. Same matching rule.
_UNTRUSTED_CONTENT_SOURCES: tuple[str, ...] = (
    "web:",
    "http:",
    "https:",
    "corpus:",
    "retrieval:",
    "llm_output:",
    "llm:",
    "tool_output:",
    "rag:",
    "external:",
)


class ContentClassifier:
    """Classify a piece of content by its declared source.

    The classifier trusts the *caller's* `source` declaration. Callers MUST
    set `source` correctly — the rest of the pipeline treats this label as
    authoritative. If a caller lies (e.g. labels LLM output as `system:`),
    that is a caller bug, not a classifier bug. Downstream sanitization still
    applies to UNTRUSTED_CONTENT regardless.
    """

    def classify(self, content: str, source: str) -> TrustLevel:
        """Return the TrustLevel for `content` given its declared `source`.

        Empty / None source -> UNTRUSTED_EXTERNAL (fail-closed: we don't know
        where it came from).
        """
        if not source or not source.strip():
            return TrustLevel.UNTRUSTED_EXTERNAL
        src = source.strip().lower()

        # Trusted control-plane: matter_id, agent_name, system, runtime, ...
        for prefix in _TRUSTED_SOURCE_PREFIXES:
            if src.startswith(prefix):
                return TrustLevel.TRUSTED_CONTROL

        # Known external content sources.
        for prefix in _UNTRUSTED_CONTENT_SOURCES:
            if src.startswith(prefix):
                return TrustLevel.UNTRUSTED_CONTENT

        # Fall back: unknown origin — highest caution tier.
        return TrustLevel.UNTRUSTED_EXTERNAL


# ---------------------------------------------------------------------------
# Prompt-injection detection
# ---------------------------------------------------------------------------

# Patterns that attempt to override agent instructions. Each tuple is
# (compiled_regex, human_label). Lowercase matching throughout.
_INJECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+(instructions?|prompts?|rules?)"),
        "ignore-previous-instructions",
    ),
    (
        # "system:" prefix that tries to spoof a system message
        re.compile(r"(^|\n)\s*system\s*:"),
        "system-prefix-spoof",
    ),
    (
        # "you are now/a/an/the <identity>" anywhere — identity rewrite
        re.compile(r"\byou\s+are\s+(now|an?|the)\b"),
        "you-are-identity-override",
    ),
    (
        re.compile(r"\bact\s+as\s+(if\s+)?(you\s+were\s+)?(an?|the)\b"),
        "act-as-identity-override",
    ),
    (
        re.compile(r"\b(disregard|forget)\s+(all\s+)?(previous|prior|above)\b"),
        "disregard-previous",
    ),
    (
        re.compile(r"\bnew\s+(instructions?|rules?)\s*:\s*", re.IGNORECASE),
        "new-instructions-injection",
    ),
    (
        # "From now on, ..." identity rewrites
        re.compile(r"\bfrom\s+now\s+on[,\s]+(you\s+are|act\s+as|behave\s+as)\b"),
        "from-now-on-override",
    ),
    (
        # Attempts to reveal or override the system prompt
        re.compile(r"\b(reveal|show|print|repeat|output)\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?)\b"),
        "prompt-exfiltration",
    ),
)


def is_prompt_injection(text: str) -> tuple[bool, str]:
    """Detect whether `text` contains prompt-injection patterns.

    Returns (detected: bool, matched_pattern_label: str).
    `matched_pattern_label` is "" when nothing matched.
    """
    if not text:
        return (False, "")
    lowered = text.lower()
    for pattern, label in _INJECTION_PATTERNS:
        if pattern.search(lowered):
            return (True, label)
    return (False, "")


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

_UNTRUSTED_START = "[UNTRUSTED_CONTENT_START]"
_UNTRUSTED_END = "[UNTRUSTED_CONTENT_END]"


def _strip_instruction_patterns(content: str) -> str:
    """Remove (not just escape) lines that match injection patterns.

    We strip the *entire line* on which an injection pattern is detected, not
    just the matching substring. Partial-removal risks leaving a malformed
    fragment that still influences the agent. Stripping the whole line is the
    safer, fail-closed choice.
    """
    if not content:
        return ""
    cleaned_lines: list[str] = []
    for line in content.splitlines():
        detected, _label = is_prompt_injection(line)
        if detected:
            # Replace the offending line with a marker so the agent sees a
            # gap existed, but no injection payload survives.
            cleaned_lines.append("[CONTENT REDACTED: INJECTION PATTERN]")
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def sanitize_for_agent(content: str) -> str:
    """Sanitize untrusted content before it enters an agent prompt.

    Behavior:
    - If `content` looks like an instruction-injection attempt, the offending
      lines are redacted.
    - The remaining content is wrapped in explicit boundary markers so the
      agent can tell data apart from instructions:
        [UNTRUSTED_CONTENT_START]...[UNTRUSTED_CONTENT_END]
    - Trusted-control content is returned as-is (no wrapping) — the caller is
      expected to only call this on UNTRUSTED_CONTENT. We do not re-classify
      here because the caller has already classified. If callers misuse this
      on trusted content, the worst case is over-wrapping — safe.

    Returns the sanitized string. Empty input -> empty string (no markers).
    """
    if not content:
        return ""
    stripped = _strip_instruction_patterns(content)
    # Even after stripping, wrap the remaining body — the agent must be able
    # to tell "this is data, not instructions" regardless of stripping.
    return f"{_UNTRUSTED_START}\n{stripped}\n{_UNTRUSTED_END}"


# ---------------------------------------------------------------------------
# Convenience facade
# ---------------------------------------------------------------------------


def classify_and_sanitize(
    content: str,
    source: str,
    *,
    classifier: ContentClassifier | None = None,
) -> dict[str, Any]:
    """One-shot helper: classify + (if needed) sanitize.

    Returns a small dict so callers can audit the decision:
        {
          "trust_level": TrustLevel,
          "sanitized": str,
          "injection_detected": bool,
          "injection_label": str,
        }
    """
    clf = classifier or ContentClassifier()
    trust = clf.classify(content, source)

    if trust == TrustLevel.TRUSTED_CONTROL:
        # Trusted content flows through unchanged.
        inj, label = is_prompt_injection(content)
        return {
            "trust_level": trust,
            "sanitized": content,
            "injection_detected": inj,
            "injection_label": label,
        }

    inj, label = is_prompt_injection(content)
    sanitized = sanitize_for_agent(content)
    return {
        "trust_level": trust,
        "sanitized": sanitized,
        "injection_detected": inj,
        "injection_label": label,
    }
