"""Best-effort pull of the claude-journal repo.

Phase 1: pull-only. Phase 2 added memory/skill sync; Phase 3 surfaces
proposals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tools.journal.push import _run_git

_BUFFER_LOG = Path.home() / ".claude" / "journal-buffer.log"


def _log_failure(message: str) -> None:
    try:
        _BUFFER_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_BUFFER_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] pull_journal: {message}\n")
    except Exception:
        pass


def pull_journal(journal_repo: Path) -> bool:
    """Pull-rebase the journal repo. Returns True iff the pull succeeded.

    --autostash keeps the rebase from aborting on an unrelated dirty
    working tree (e.g. git-crypt smudge-filter artefacts on .gitkeep
    blobs under encrypted paths after `git-crypt unlock`). On failure
    we append to the buffer log so the next failure isn't silent — the
    SessionStart hook discards our return value.
    """
    if not (journal_repo / ".git").exists():
        return False
    result = _run_git(
        ["git", "pull", "--rebase", "--autostash", "--quiet"],
        cwd=journal_repo,
    )
    if result.returncode != 0:
        stderr_lines = (result.stderr or "").strip().splitlines()
        tail = " | ".join(stderr_lines[-3:]) if stderr_lines else f"rc={result.returncode}"
        _log_failure(tail)
        return False
    return True
