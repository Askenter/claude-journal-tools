from pathlib import Path
from tools.journal.sync_skills import (
    sync_global_skills,
    sync_project_skills,
    sync_all_skills,
)


def _write_skill(parent: Path, name: str, body: str = "skill body") -> None:
    skill_dir = parent / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: when to use {name}\n"
        "---\n\n"
        f"{body}\n"
    )


def test_sync_global_copies_skill_dirs(tmp_path: Path):
    journal = tmp_path / "journal"
    _write_skill(journal / "skills" / "global", "condition-based-waiting")
    _write_skill(journal / "skills" / "global", "rooting-out-flake")
    user_dir = tmp_path / "claude"

    result = sync_global_skills(
        journal_repo=journal,
        claude_skills_dir=user_dir / "skills",
    )
    assert (user_dir / "skills" / "condition-based-waiting" / "SKILL.md").exists()
    assert (user_dir / "skills" / "rooting-out-flake" / "SKILL.md").exists()
    assert sorted(result.new_skills) == ["condition-based-waiting", "rooting-out-flake"]


def test_sync_global_is_idempotent(tmp_path: Path):
    journal = tmp_path / "journal"
    _write_skill(journal / "skills" / "global", "skill-a", body="v1")
    user_dir = tmp_path / "claude"

    sync_global_skills(journal_repo=journal, claude_skills_dir=user_dir / "skills")
    second = sync_global_skills(journal_repo=journal, claude_skills_dir=user_dir / "skills")
    assert second.new_skills == []
    assert second.updated_skills == []


def test_sync_global_updates_when_content_changes(tmp_path: Path):
    journal = tmp_path / "journal"
    _write_skill(journal / "skills" / "global", "skill-a", body="v1")
    user_dir = tmp_path / "claude"
    sync_global_skills(journal_repo=journal, claude_skills_dir=user_dir / "skills")

    _write_skill(journal / "skills" / "global", "skill-a", body="v2")
    second = sync_global_skills(journal_repo=journal, claude_skills_dir=user_dir / "skills")
    assert second.updated_skills == ["skill-a"]
    text = (user_dir / "skills" / "skill-a" / "SKILL.md").read_text()
    assert "v2" in text


def test_sync_project_skills_lands_per_project(tmp_path: Path):
    journal = tmp_path / "journal"
    _write_skill(journal / "skills" / "projects" / "-home-you-myproject", "myproject-only")
    projects_dir = tmp_path / "claude" / "projects"

    results = sync_project_skills(journal_repo=journal, claude_projects_dir=projects_dir)
    target = projects_dir / "-home-you-myproject" / ".claude" / "skills" / "myproject-only" / "SKILL.md"
    assert target.exists()
    assert any(r.scope == "project:-home-you-myproject" for r in results)


def test_sync_all_skills_returns_empty_when_no_skills_dir(tmp_path: Path):
    journal = tmp_path / "journal"
    journal.mkdir()
    results = sync_all_skills(
        journal_repo=journal,
        claude_user_dir=tmp_path / "user",
        claude_projects_dir=tmp_path / "projects",
    )
    assert results == []


def test_sync_all_skills_walks_global_and_projects(tmp_path: Path):
    journal = tmp_path / "journal"
    _write_skill(journal / "skills" / "global", "g1")
    _write_skill(journal / "skills" / "projects" / "p", "p1")
    user = tmp_path / "user"
    projects = tmp_path / "projects"

    results = sync_all_skills(
        journal_repo=journal,
        claude_user_dir=user,
        claude_projects_dir=projects,
    )
    assert (user / "skills" / "g1" / "SKILL.md").exists()
    assert (projects / "p" / ".claude" / "skills" / "p1" / "SKILL.md").exists()
    scopes = sorted(r.scope for r in results)
    assert scopes == ["global", "project:p"]
