"""Mirror consolidated memories from the journal repo into Claude Code's
auto-memory tree on this device.

Source: `<journal>/memories/<project>/*.md` — produced by the central
nightly routine.

Destination: `~/.claude/projects/<project>/memory/` — read by Claude Code
via the auto-memory system, indexed by `MEMORY.md`.

Two safety constraints:

1. `feedback` memories are NEVER auto-applied here. They are behavioral
   rules; same blast radius as a CLAUDE.md edit. The routine writes them
   to `proposals/` instead, and Phase 3's `/journal accept` flow surfaces
   them for the user to confirm. We skip them defensively even though
   the routine shouldn't put them under `memories/` in the first place.

2. Device-original MEMORY.md content is never destroyed. We append
   journal-produced entries that aren't already present, but leave any
   existing user-written entries untouched. Individual memory files
   sourced from the journal are copied by name; if a file with the
   same name already exists on the device, it is overwritten (so the
   journal stays authoritative for memories it produced).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SyncResult:
    project: str
    new_files: list[str]
    updated_files: list[str]
    skipped_feedback: list[str]
    appended_index_lines: int


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse the YAML-ish frontmatter at the top of a memory file. Only
    captures simple `key: value` pairs — that's all the auto-memory format
    uses, so no full YAML parser needed."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _is_feedback_memory(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return _parse_frontmatter(text).get("type") == "feedback"


def _list_journal_memory_files(journal_project_dir: Path) -> list[Path]:
    """Return memory files under a journal project dir, excluding the index
    (MEMORY.md) — the index is appended into separately."""
    return sorted(
        p for p in journal_project_dir.glob("*.md")
        if p.name != "MEMORY.md" and p.is_file()
    )


def _read_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _entries_in_index(text: str) -> set[str]:
    """Return the set of filenames already linked from a MEMORY.md so we
    don't duplicate index lines on re-sync."""
    return set(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))


def _journal_index_lines(journal_index_text: str) -> list[str]:
    """Return the list of `- [Title](file.md) — hook` index lines from the
    journal's MEMORY.md, in original order."""
    lines = []
    for raw in journal_index_text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("- [") and "](" in stripped:
            lines.append(stripped)
    return lines


def _ensure_device_index(device_index: Path, project: str) -> str:
    """Make sure the device's MEMORY.md exists with a heading. Returns the
    current contents."""
    if device_index.exists():
        return device_index.read_text(encoding="utf-8")
    header = f"# {project} Memory\n\n"
    device_index.write_text(header)
    return header


def _append_index_entries(device_index: Path, entries: list[str]) -> int:
    if not entries:
        return 0
    text = device_index.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    text += "\n".join(entries) + "\n"
    device_index.write_text(text)
    return len(entries)


def sync_project_memories(
    *,
    journal_project_dir: Path,
    device_project_memory_dir: Path,
    project: str,
) -> SyncResult:
    """Mirror one project's memories from the journal to the device tree."""
    device_project_memory_dir.mkdir(parents=True, exist_ok=True)
    new_files: list[str] = []
    updated_files: list[str] = []
    skipped_feedback: list[str] = []

    for src in _list_journal_memory_files(journal_project_dir):
        if _is_feedback_memory(src):
            skipped_feedback.append(src.name)
            continue
        dest = device_project_memory_dir / src.name
        existed = dest.exists()
        try:
            content = src.read_text(encoding="utf-8")
        except OSError:
            continue
        if existed and dest.read_text(encoding="utf-8") == content:
            continue
        dest.write_text(content)
        (updated_files if existed else new_files).append(src.name)

    device_index = device_project_memory_dir / "MEMORY.md"
    _ensure_device_index(device_index, project)
    journal_index = journal_project_dir / "MEMORY.md"
    appended_count = 0
    if journal_index.exists():
        device_text = device_index.read_text(encoding="utf-8")
        already = _entries_in_index(device_text)
        new_entries: list[str] = []
        for line in _journal_index_lines(_read_or_empty(journal_index)):
            # Dedupe on the link TARGET (the `](target)` part), matching how
            # `_entries_in_index` keys `already`. Anchoring on `](` is required:
            # a bare `\(...\)` grabs the first parenthetical, which for a title
            # like "... (2026-05-01)" is the date — it never matches `already`,
            # so the entry is re-appended on every sync.
            match = re.search(r"\]\(([^)]+)\)", line)
            if not match:
                continue
            filename = match.group(1)
            if filename in already or filename == "MEMORY.md":
                continue
            new_entries.append(line)
            already.add(filename)
        appended_count = _append_index_entries(device_index, new_entries)

    return SyncResult(
        project=project,
        new_files=new_files,
        updated_files=updated_files,
        skipped_feedback=skipped_feedback,
        appended_index_lines=appended_count,
    )


def sync_all_memories(
    *,
    journal_repo: Path,
    claude_projects_dir: Path,
) -> list[SyncResult]:
    """Walk every project under journal/memories/ and sync each into the
    device's auto-memory tree. Missing source dir is fine — returns []."""
    src_root = journal_repo / "memories"
    if not src_root.exists():
        return []
    results: list[SyncResult] = []
    for project_dir in sorted(p for p in src_root.iterdir() if p.is_dir()):
        device_dir = claude_projects_dir / project_dir.name / "memory"
        results.append(sync_project_memories(
            journal_project_dir=project_dir,
            device_project_memory_dir=device_dir,
            project=project_dir.name,
        ))
    return results
