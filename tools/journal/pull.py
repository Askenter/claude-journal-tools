"""Best-effort pull of the claude-journal repo.

Phase 1: pull-only. Phase 2 will add memory/skill sync; Phase 3 will surface
proposals.
"""
from pathlib import Path

from tools.journal.push import _run_git


def pull_journal(journal_repo: Path) -> bool:
    """Pull-rebase the journal repo. Returns True iff the pull succeeded."""
    if not (journal_repo / ".git").exists():
        return False
    result = _run_git(["git", "pull", "--rebase", "--quiet"], cwd=journal_repo)
    return result.returncode == 0
