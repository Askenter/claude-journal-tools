"""SessionStart hook entrypoint.

Phase 3 v2: pulls claude-journal, mirrors consolidated memories + skills
into Claude Code's trees on this device, and surfaces any pending
proposals for the current project as `additionalContext` so the next
assistant turn sees them.

Always exits 0 so it never blocks the user.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Self-locate the project root so imports work regardless of cwd/PYTHONPATH.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.journal.encryption import is_repo_unlocked
from tools.journal.paths import journal_repo_path
from tools.journal.pull import pull_journal
from tools.journal.surface_proposals import build_proposal_context
from tools.journal.sync_memories import sync_all_memories
from tools.journal.sync_skills import sync_all_skills

LOCKED_REPO_WARNING = (
    "WARNING: claude-journal is locked on this device — distilled "
    "memories, skills, and proposals will not surface correctly. "
    "Run `git-crypt unlock ~/.claude/journal/git-crypt.key` to fix."
)

STALE_REPO_WARNING = (
    "WARNING: claude-journal pull failed on this SessionStart — distilled "
    "memories, skills, and proposals shown below may be stale. Check "
    "`~/.claude/journal-buffer.log` for the git stderr, and inspect "
    "`git -C ~/claude-journal status` for a dirty worktree or divergence."
)


def _read_payload_safe() -> dict:
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def _log_error(message: str) -> None:
    try:
        log = Path.home() / ".claude" / "journal-buffer.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {message}\n")
    except Exception:
        pass


def _emit_additional_context(text: str) -> None:
    """Stream the hookSpecificOutput JSON Claude Code reads from the
    SessionStart hook so the surfaced text becomes a system reminder in
    the next assistant turn."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def main() -> int:
    payload = _read_payload_safe()
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    pull_ok = False
    try:
        journal = journal_repo_path()
        pull_ok = bool(pull_journal(journal))
    except Exception as exc:
        _log_error(f"on_start pull failed: {exc!r}")
        return 0

    claude_user = Path.home() / ".claude"
    claude_projects = claude_user / "projects"

    try:
        sync_all_memories(journal_repo=journal, claude_projects_dir=claude_projects)
    except Exception as exc:
        _log_error(f"sync_memories failed: {exc!r}")
    try:
        sync_all_skills(
            journal_repo=journal,
            claude_user_dir=claude_user,
            claude_projects_dir=claude_projects,
        )
    except Exception as exc:
        _log_error(f"sync_skills failed: {exc!r}")

    segments: list[str] = []
    if not pull_ok:
        segments.append(STALE_REPO_WARNING)
    try:
        if not is_repo_unlocked(journal):
            segments.append(LOCKED_REPO_WARNING)
    except Exception as exc:
        _log_error(f"is_repo_unlocked failed: {exc!r}")

    if cwd:
        try:
            ctx = build_proposal_context(journal_repo=journal, cwd=cwd)
            if ctx:
                segments.append(ctx)
        except Exception as exc:
            _log_error(f"surface_proposals failed: {exc!r}")

    if segments:
        _emit_additional_context("\n\n".join(segments))

    return 0


if __name__ == "__main__":
    sys.exit(main())
