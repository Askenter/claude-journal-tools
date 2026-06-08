"""Surface pending journal proposals to Claude via SessionStart's
`additionalContext`.

The central routine writes proposals (Track 1b feedback memories, Track 2
new-skill suggestions, Track 3 CLAUDE.md edits) under
`<journal>/proposals/<date>-<project>.md`. On SessionStart for that project,
we want the next assistant turn to see them so the user can act via
`/journal accept|skip|edit`.

We build a short markdown block listing the pending proposals for the current
project — one line per `## ` entry, each tagged with its type (new skill /
feedback rule / CLAUDE.md edit) — and return it as the
hookSpecificOutput.additionalContext value (read by Claude Code from the
hook's stdout).

Proposal filenames follow `<YYYY-MM-DD>-<project-key>.md`. The current
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _first_nonempty(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _iter_entries(text: str) -> list[tuple[str, str]]:
    """Split a proposal file into (heading, entry_text) pairs by `## `
    headings. Any content before the first heading is ignored."""
    entries: list[tuple[str, list[str]]] = []
    current: Optional[tuple[str, list[str]]] = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                entries.append(current)
            current = (line[3:].strip(), [line])
        elif current is not None:
            current[1].append(line)
    if current is not None:
        entries.append(current)
    return [(heading, "\n".join(body)) for heading, body in entries]


def _entry_label(heading: str, body: str) -> str:
    """Classify one proposal entry for display."""
    h = heading.lower()
    b = body.lower()
    if h.startswith("new skill") or "kind: new-skill" in b or "kind:** new-skill" in b:
        return "new skill"
    if "feedback" in h or "type: feedback" in b:
        return "feedback rule"
    if "claude.md" in h or "claude.md" in b or "target:" in b:
        return "CLAUDE.md edit"
    return "proposal"


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
        text = _read_text(path)
        entries = _iter_entries(text)
        if not entries:
            summary = _first_nonempty(text) or path.name
            lines.append(f"- [proposal] {summary} (`{path}`)")
            continue
        for heading, body in entries:
            label = _entry_label(heading, body)
            lines.append(f"- [{label}] {heading} (`{path}`)")
    lines.extend([
        "",
        "These are new skills, behavioral rules, or CLAUDE.md edits the "
        "consolidator extracted from recent sessions. They are NOT "
        "auto-applied.",
        "",
        "Run `/journal accept`, `/journal skip`, or `/journal edit` to "
        "review and act on them.",
    ])
    return "\n".join(lines)
