"""Surface pending journal proposals to Claude via SessionStart's
`additionalContext`.

The central routine writes proposals (Track 1b feedback memories,
Track 3 CLAUDE.md edits) under `<journal>/proposals/<date>-<project>.md`.
On SessionStart for that project, we want the next assistant turn to see
them so the user can act via `/journal accept|skip|edit`.

We build a short markdown block that lists the pending proposals for the
current project, including their on-disk path, and return it as the
hookSpecificOutput.additionalContext value (read by Claude Code from
the hook's stdout).

Proposals filenames follow `<YYYY-MM-DD>-<project-key>.md`. The current
project's key comes from the SessionStart payload's `cwd` (replace `/`
with `-`, matching the breadcrumb extractor).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def project_key_from_cwd(cwd: str) -> str:
    """Mirror the project-key derivation used by the Stop hook so proposal
    files land under the same key the breadcrumbs use."""
    return cwd.replace("/", "-")


def _list_proposals_for_project(proposals_dir: Path, project_key: str) -> list[Path]:
    if not proposals_dir.exists():
        return []
    matches: list[Path] = []
    for path in sorted(proposals_dir.glob("*.md")):
        # Filename is "<YYYY-MM-DD>-<project>.md"
        stem = path.stem  # without .md
        if stem.endswith("-" + project_key) or stem == project_key:
            matches.append(path)
    return matches


def _summary_line(path: Path) -> str:
    """Pull a one-line summary out of the proposal file. We try the first
    `## ` heading; failing that, the first non-empty line."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.name
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            return stripped[3:].strip()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return path.name


def build_proposal_context(*, journal_repo: Path, cwd: str) -> Optional[str]:
    """Return the additionalContext string to surface, or None if there
    are no pending proposals for this project."""
    project_key = project_key_from_cwd(cwd)
    proposals = _list_proposals_for_project(journal_repo / "proposals", project_key)
    if not proposals:
        return None
    lines = [
        "📓 claude-journal has pending proposals for this project:",
        "",
    ]
    for path in proposals:
        summary = _summary_line(path)
        lines.append(f"- `{path}` — {summary}")
    lines.extend([
        "",
        "These are behavioral rules or CLAUDE.md edits the consolidator "
        "extracted from recent sessions. They are NOT auto-applied.",
        "",
        "Run `/journal accept`, `/journal skip`, or `/journal edit` to "
        "review and act on them.",
    ])
    return "\n".join(lines)
