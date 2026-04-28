"""SessionStart hook entrypoint.

Phase 3: pull claude-journal AND sync consolidated memories (non-feedback)
into Claude Code's auto-memory tree on this device.

Surfacing of feedback proposals + skills sync is still future work.

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
from tools.journal.sync_memories import sync_all_memories


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


def main() -> int:
    try:
        _ = _read_payload_safe()  # payload not used yet
        journal = journal_repo_path()
        pull_journal(journal)
        try:
            sync_all_memories(
                journal_repo=journal,
                claude_projects_dir=Path.home() / ".claude" / "projects",
            )
        except Exception as exc:
            # Memory sync is best-effort — pull already succeeded, don't
            # break the session over a sync hiccup.
            _log_error(f"sync_memories failed: {exc!r}")
    except Exception as exc:
        _log_error(f"on_start error: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
