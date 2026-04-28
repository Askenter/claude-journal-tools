"""Capture project state files (currently CLAUDE.md) into the journal so
the central routine has a source-of-truth to diff against when extracting
Track 3 (CLAUDE.md edit) proposals.

Stored at `<journal>/state/<project_key>/CLAUDE.md` — last-writer-wins
across devices. If two devices edit a project's CLAUDE.md concurrently,
the later Stop event will overwrite. That's acceptable for v1: the
`/journal accept` flow always re-reads the live device file before
applying any diff, so journal staleness can't trigger a wrong edit, only
a redundant proposal.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# Same light-touch redactions used for transcripts — defense-in-depth so
# CLAUDE.md secrets don't accidentally land in the journal repo.
_REDACTION_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),       # Anthropic / OpenAI / OAuth
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),        # GitHub PAT classic
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),  # GitHub PAT fine-grained
]


def _redact(text: str) -> str:
    for pat in _REDACTION_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _safe_project_segment(project_key: str) -> str:
    return project_key.replace("/", "_").replace("\\", "_").replace("..", "__")


def read_project_claudemd(cwd: Path) -> Optional[str]:
    """Return the redacted contents of `<cwd>/CLAUDE.md`, or None when the
    file is missing/unreadable."""
    target = cwd / "CLAUDE.md"
    if not target.is_file():
        return None
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None
    return _redact(text)


def write_state_claudemd(
    *,
    journal_repo: Path,
    project_key: str,
    content: str,
) -> Path:
    """Write the captured CLAUDE.md to the journal state tree. Returns the
    target path."""
    safe_key = _safe_project_segment(project_key)
    target_dir = journal_repo / "state" / safe_key
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "CLAUDE.md"
    target.write_text(content if content.endswith("\n") else content + "\n")
    return target
