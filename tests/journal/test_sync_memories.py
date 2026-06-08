from pathlib import Path
from tools.journal.sync_memories import (
    sync_project_memories,
    sync_all_memories,
)


def _write_memory(dir: Path, name: str, *, mem_type: str = "project", body: str = "body text") -> None:
    dir.mkdir(parents=True, exist_ok=True)
    (dir / name).write_text(
        "---\n"
        f"name: {name.replace('.md', '')}\n"
        f"description: short hook for {name}\n"
        f"type: {mem_type}\n"
        "---\n\n"
        f"{body}\n"
    )


def _write_index(dir: Path, project: str, entries: list[str]) -> None:
    text = f"# {project} Memory\n\n"
    for entry in entries:
        text += entry + "\n"
    (dir / "MEMORY.md").write_text(text)


def test_sync_copies_project_memory_files(tmp_path: Path):
    journal_dir = tmp_path / "journal" / "memories" / "-home-you-myproject"
    device_dir = tmp_path / "device" / "memory"
    _write_memory(journal_dir, "deployment.md")
    _write_memory(journal_dir, "data-counts.md")
    _write_index(journal_dir, "-home-you-myproject", [
        "- [Deployment](deployment.md) — split-node arch",
        "- [Data counts](data-counts.md) — current totals",
    ])

    result = sync_project_memories(
        journal_project_dir=journal_dir,
        device_project_memory_dir=device_dir,
        project="-home-you-myproject",
    )

    assert (device_dir / "deployment.md").exists()
    assert (device_dir / "data-counts.md").exists()
    assert sorted(result.new_files) == ["data-counts.md", "deployment.md"]
    index = (device_dir / "MEMORY.md").read_text()
    assert "deployment.md" in index
    assert "data-counts.md" in index


def test_sync_skips_feedback_memories(tmp_path: Path):
    """Feedback memories must never auto-apply via sync — they go through
    the proposal queue (Phase 3 surface)."""
    journal_dir = tmp_path / "journal" / "memories" / "p"
    device_dir = tmp_path / "device" / "memory"
    _write_memory(journal_dir, "no-mocks.md", mem_type="feedback")
    _write_memory(journal_dir, "deployment.md", mem_type="project")

    result = sync_project_memories(
        journal_project_dir=journal_dir,
        device_project_memory_dir=device_dir,
        project="p",
    )

    assert (device_dir / "deployment.md").exists()
    assert not (device_dir / "no-mocks.md").exists()
    assert result.skipped_feedback == ["no-mocks.md"]


def test_sync_preserves_existing_device_memory_index_entries(tmp_path: Path):
    """Device's existing MEMORY.md content (user-written entries) must
    survive a sync — we append journal entries, never overwrite the file
    wholesale."""
    journal_dir = tmp_path / "journal" / "memories" / "p"
    device_dir = tmp_path / "device" / "memory"
    device_dir.mkdir(parents=True)
    (device_dir / "MEMORY.md").write_text(
        "# p Memory\n\n"
        "- [User-written](user.md) — never touch this\n"
    )
    _write_memory(journal_dir, "from-routine.md")
    _write_index(journal_dir, "p", ["- [Routine fact](from-routine.md) — added by routine"])

    sync_project_memories(
        journal_project_dir=journal_dir,
        device_project_memory_dir=device_dir,
        project="p",
    )
    text = (device_dir / "MEMORY.md").read_text()
    assert "[User-written](user.md)" in text
    assert "[Routine fact](from-routine.md)" in text


def test_sync_does_not_duplicate_index_entries_on_resync(tmp_path: Path):
    journal_dir = tmp_path / "journal" / "memories" / "p"
    device_dir = tmp_path / "device" / "memory"
    _write_memory(journal_dir, "fact.md")
    _write_index(journal_dir, "p", ["- [Fact](fact.md) — one"])

    sync_project_memories(
        journal_project_dir=journal_dir,
        device_project_memory_dir=device_dir,
        project="p",
    )
    sync_project_memories(
        journal_project_dir=journal_dir,
        device_project_memory_dir=device_dir,
        project="p",
    )
    text = (device_dir / "MEMORY.md").read_text()
    assert text.count("[Fact](fact.md)") == 1


def test_sync_dedupes_when_link_text_contains_parens(tmp_path: Path):
    """Regression: an index entry whose link TEXT contains parentheses (e.g. a
    `(date)`) must still dedupe on resync. The dedupe key is the link TARGET —
    the part after `](` — not the first parenthesized group, which would be the
    date and never match, re-appending the line every SessionStart."""
    journal_dir = tmp_path / "journal" / "memories" / "p"
    device_dir = tmp_path / "device" / "memory"
    _write_memory(journal_dir, "pull-push-fix.md")
    _write_index(journal_dir, "p", [
        "- [pull.py and push.py — fixes (2026-05-01)](pull-push-fix.md) — details",
    ])

    for _ in range(3):  # three SessionStarts
        sync_project_memories(
            journal_project_dir=journal_dir,
            device_project_memory_dir=device_dir,
            project="p",
        )

    text = (device_dir / "MEMORY.md").read_text()
    assert text.count("(pull-push-fix.md)") == 1


def test_sync_overwrites_journal_owned_files_when_content_changes(tmp_path: Path):
    """A memory file that was originally placed by a sync should be updated
    when the journal version changes (otherwise consolidated facts go
    stale)."""
    journal_dir = tmp_path / "journal" / "memories" / "p"
    device_dir = tmp_path / "device" / "memory"
    _write_memory(journal_dir, "fact.md", body="initial")
    _write_index(journal_dir, "p", ["- [Fact](fact.md) — one"])
    sync_project_memories(
        journal_project_dir=journal_dir,
        device_project_memory_dir=device_dir,
        project="p",
    )

    # Journal updates the same file
    _write_memory(journal_dir, "fact.md", body="updated content")
    result = sync_project_memories(
        journal_project_dir=journal_dir,
        device_project_memory_dir=device_dir,
        project="p",
    )
    assert "fact.md" in result.updated_files
    assert "updated content" in (device_dir / "fact.md").read_text()


def test_sync_all_walks_every_project(tmp_path: Path):
    journal = tmp_path / "journal"
    device_projects = tmp_path / "claude" / "projects"
    _write_memory(journal / "memories" / "proj-a", "a.md")
    _write_memory(journal / "memories" / "proj-b", "b.md")
    _write_index(journal / "memories" / "proj-a", "proj-a", ["- [a](a.md) — x"])
    _write_index(journal / "memories" / "proj-b", "proj-b", ["- [b](b.md) — y"])

    results = sync_all_memories(
        journal_repo=journal,
        claude_projects_dir=device_projects,
    )

    assert {r.project for r in results} == {"proj-a", "proj-b"}
    assert (device_projects / "proj-a" / "memory" / "a.md").exists()
    assert (device_projects / "proj-b" / "memory" / "b.md").exists()


def test_sync_all_returns_empty_when_no_memories_dir(tmp_path: Path):
    """Brand-new journal repo without a memories/ dir yet must not crash."""
    journal = tmp_path / "journal"
    journal.mkdir()
    results = sync_all_memories(
        journal_repo=journal,
        claude_projects_dir=tmp_path / "claude" / "projects",
    )
    assert results == []


def test_sync_creates_minimal_index_when_journal_index_missing(tmp_path: Path):
    """If the journal didn't write a MEMORY.md (shouldn't happen, but be
    resilient), the sync still copies files and ensures a device index
    header exists."""
    journal_dir = tmp_path / "journal" / "memories" / "p"
    device_dir = tmp_path / "device" / "memory"
    _write_memory(journal_dir, "fact.md")
    # No journal MEMORY.md

    sync_project_memories(
        journal_project_dir=journal_dir,
        device_project_memory_dir=device_dir,
        project="p",
    )
    assert (device_dir / "fact.md").exists()
    assert (device_dir / "MEMORY.md").exists()
    assert (device_dir / "MEMORY.md").read_text().startswith("# p Memory")
