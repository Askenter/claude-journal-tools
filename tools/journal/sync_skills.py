"""Mirror consolidated skills from the journal repo into Claude Code's
skills tree on this device.

Sources:
- `<journal>/skills/global/<name>/` — distilled cross-project skills
- `<journal>/skills/projects/<project>/<name>/` — project-scoped skills

Destinations:
- Global: `~/.claude/skills/<name>/` (visible to every project)
- Per-project: `~/.claude/projects/<project>/.claude/skills/<name>/`

Skills are description-gated (Claude only invokes them when the
description matches the task), so blast radius is bounded — that's why
the design lets them auto-apply without a proposal queue.

Each skill is a directory containing at least `SKILL.md`. We mirror the
whole directory shallow-recursively (one level deep is enough for the
v1 layout).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillSyncResult:
    scope: str  # "global" or "project:<name>"
    new_skills: list[str]
    updated_skills: list[str]


def _list_skill_dirs(parent: Path) -> list[Path]:
    if not parent.exists():
        return []
    return sorted(p for p in parent.iterdir() if p.is_dir())


def _dirs_have_same_content(a: Path, b: Path) -> bool:
    """Cheap structural equality check — same set of files, same content
    byte-for-byte. Skips dotfiles / pycache."""
    if not a.exists() or not b.exists():
        return False
    files_a = {f.relative_to(a) for f in a.rglob("*") if f.is_file() and "__pycache__" not in f.parts}
    files_b = {f.relative_to(b) for f in b.rglob("*") if f.is_file() and "__pycache__" not in f.parts}
    if files_a != files_b:
        return False
    for rel in files_a:
        if (a / rel).read_bytes() != (b / rel).read_bytes():
            return False
    return True


def _mirror_skill(src: Path, dst: Path) -> tuple[bool, bool]:
    """Copy src skill dir to dst. Returns (added_new, updated_existing)."""
    existed = dst.exists()
    if existed and _dirs_have_same_content(src, dst):
        return (False, False)
    if existed:
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return (not existed, existed)


def sync_global_skills(
    *,
    journal_repo: Path,
    claude_skills_dir: Path,
) -> SkillSyncResult:
    """Mirror journal/skills/global/<name>/ → claude_skills_dir/<name>/."""
    src_root = journal_repo / "skills" / "global"
    new: list[str] = []
    updated: list[str] = []
    for skill_dir in _list_skill_dirs(src_root):
        added_new, was_updated = _mirror_skill(skill_dir, claude_skills_dir / skill_dir.name)
        if added_new:
            new.append(skill_dir.name)
        elif was_updated:
            updated.append(skill_dir.name)
    return SkillSyncResult(scope="global", new_skills=new, updated_skills=updated)


def sync_project_skills(
    *,
    journal_repo: Path,
    claude_projects_dir: Path,
) -> list[SkillSyncResult]:
    """For each journal/skills/projects/<project>/, mirror its skills into
    claude_projects_dir/<project>/.claude/skills/<name>/."""
    src_root = journal_repo / "skills" / "projects"
    if not src_root.exists():
        return []
    results: list[SkillSyncResult] = []
    for project_dir in sorted(p for p in src_root.iterdir() if p.is_dir()):
        new: list[str] = []
        updated: list[str] = []
        dst_skills_dir = claude_projects_dir / project_dir.name / ".claude" / "skills"
        dst_skills_dir.mkdir(parents=True, exist_ok=True)
        for skill_dir in _list_skill_dirs(project_dir):
            added_new, was_updated = _mirror_skill(skill_dir, dst_skills_dir / skill_dir.name)
            if added_new:
                new.append(skill_dir.name)
            elif was_updated:
                updated.append(skill_dir.name)
        results.append(SkillSyncResult(
            scope=f"project:{project_dir.name}",
            new_skills=new,
            updated_skills=updated,
        ))
    return results


def sync_all_skills(
    *,
    journal_repo: Path,
    claude_user_dir: Path,
    claude_projects_dir: Path,
) -> list[SkillSyncResult]:
    """Run both global and per-project skill sync. Brand-new repos without
    a skills/ tree return []."""
    if not (journal_repo / "skills").exists():
        return []
    results = [sync_global_skills(
        journal_repo=journal_repo,
        claude_skills_dir=claude_user_dir / "skills",
    )]
    results.extend(sync_project_skills(
        journal_repo=journal_repo,
        claude_projects_dir=claude_projects_dir,
    ))
    return results
