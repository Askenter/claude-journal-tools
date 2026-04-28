"""Extract human-readable transcript text from a Claude Code JSONL transcript.

The structured breadcrumb captures *what* happened (files, skills, prompt);
the transcript text captures *why* (decisions, preferences, behavioral
rules) — material the central routine needs for memory and skill
distillation.

We keep only the conversational message bodies (user prose + assistant
prose), drop tool calls/results since they balloon the size and don't
help memory extraction. Final output is markdown, tail-truncated to a
budget (default 30 KB) so older content is dropped first when over.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Default size budget for the transcript file pushed alongside a breadcrumb.
# 30 KB ≈ ~7,500 words of conversational text — enough for memory/skill
# extraction without bloating the journal repo.
DEFAULT_BUDGET_BYTES = 30_000

# Light-touch redactions for things that should never end up in the journal
# even on a private repo: API keys and OAuth tokens. Not a security boundary,
# just a defense-in-depth habit.
_REDACTION_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),       # Anthropic / OpenAI / OAuth
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),        # GitHub PAT classic
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),  # GitHub PAT fine-grained
]


def _redact(text: str) -> str:
    for pat in _REDACTION_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _stringify_content(content: object) -> str:
    """Pull plain text out of a Claude Code message's content field.

    Schema variants we accept:
    - str: the text itself
    - list of dicts: keep entries with type='text', drop tool_use/tool_result
    - anything else: ignored
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                t = item.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts)
    return ""


def _format_entry(role: str, body: str) -> str | None:
    body = body.strip()
    if not body:
        return None
    return f"## {role}\n\n{body}\n"


def _iter_message_blocks(transcript_path: Path):
    """Yield ('User'|'Assistant', text) tuples in chronological order."""
    try:
        raw = transcript_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = entry.get("type")
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        body = _stringify_content(msg.get("content"))
        if kind == "user":
            yield ("User", body)
        elif kind == "assistant":
            yield ("Assistant", body)


def extract_transcript_text(
    transcript_path: Path,
    *,
    budget_bytes: int = DEFAULT_BUDGET_BYTES,
) -> str:
    """Return a markdown-formatted, tail-truncated transcript suitable for
    pushing to the journal repo. Empty string if the path is missing or
    contains no extractable text."""
    blocks: list[str] = []
    for role, body in _iter_message_blocks(transcript_path):
        formatted = _format_entry(role, body)
        if formatted is not None:
            blocks.append(formatted)
    if not blocks:
        return ""

    text = "\n".join(blocks)
    text = _redact(text)
    if len(text.encode("utf-8")) <= budget_bytes:
        return text

    # Tail-truncate by dropping leading entries until we fit the budget.
    while blocks and len("\n".join(blocks).encode("utf-8")) > budget_bytes:
        blocks.pop(0)
    if not blocks:
        return ""
    truncated = "_(earlier conversation truncated to fit budget)_\n\n" + "\n".join(blocks)
    return _redact(truncated)
