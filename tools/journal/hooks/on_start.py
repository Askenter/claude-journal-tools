"""SessionStart hook entrypoint.

Phase 3 v2: pulls claude-journal, mirrors consolidated memories + skills
into Claude Code's trees on this device, and surfaces any pending
proposals for the current project as `additionalContext` so the next
assistant turn sees them.

Always exits 0 so it never blocks the user.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Self-locate the project root so imports work regardless of cwd/PYTHONPATH.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.journal.paths import journal_repo_path
from tools.journal.pull import pull_journal
from tools.journal.surface_proposals import build_proposal_context
from tools.journal.sync_memories import sync_all_memories
from tools.journal.sync_skills import sync_all_skills


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
    try:
        journal = journal_repo_path()
        pull_journal(journal)
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

    if cwd:
        try:
            ctx = build_proposal_context(journal_repo=journal, cwd=cwd)
            if ctx:
                _emit_additional_context(ctx)
        except Exception as exc:
            _log_error(f"surface_proposals failed: {exc!r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
