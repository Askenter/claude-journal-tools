"""On-demand consolidation orchestrator for `/journal consolidate`.

Runnable as `python3 "$TOOLS/tools/journal/consolidate.py" <subcommand>`. The
mechanical work lives here so Claude never eyeballs the raw/ vs digests/ diff;
the distillation itself (Tracks 0-3) is the current session's Claude following
the data repo's `consolidator/ROUTINE.md`.

Subcommands
-----------
plan      Flush the live session into raw/, pull, verify the repo is unlocked,
          compute which dates still need consolidating, and print a JSON plan.
finalize  Stage the derived dirs, skip-if-empty, commit and push.

The two are split so the LLM distillation sits cleanly between them.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Self-locate the project root so `tools.journal.X` imports work regardless of
# how Claude Code invokes this script (no PYTHONPATH or cwd assumed).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.journal.capture import capture_session, log_error
from tools.journal.encryption import is_repo_unlocked
from tools.journal.flushed import mark_flushed
from tools.journal.paths import (
    flushed_sessions_path,
    journal_repo_path,
    read_device_name,
)
from tools.journal.pull import pull_journal
from tools.journal.push import _run_git

LOOKBACK_DAYS = 14
DERIVED_PATHS = ["digests", "memories", "proposals", "skills", "CHANGELOG.md"]


def live_transcript_path(session_id: str, cwd: str | None = None) -> Path | None:
    """Locate the live session's transcript jsonl.

    Fast path: derive `~/.claude/projects/<cwd-slug>/<sid>.jsonl`. Fallback:
    the session id is globally unique, so glob it across every project dir,
    which sidesteps any project-directory sanitization quirk.
    """
    projects = Path.home() / ".claude" / "projects"
    derived: Path | None = None
    if cwd:
        derived = projects / cwd.replace("/", "-") / f"{session_id}.jsonl"
        if derived.exists():
            return derived
    matches = sorted(projects.glob(f"*/{session_id}.jsonl"))
    if matches:
        return matches[0]
    return derived


def flush_current_session() -> str | None:
    """Capture the session this process is running inside into raw/, so the
    on-demand consolidation includes it. Marks the id as flushed so the later
    Stop hook won't re-write it. Best-effort; returns the session id on a
    capture attempt, else None. The journal repo is resolved internally by
    capture_session, so no repo argument is needed here."""
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session_id:
        return None
    cwd = os.getcwd()
    transcript = live_transcript_path(session_id, cwd)
    if transcript is None or not transcript.exists():
        log_error(f"consolidate flush: no transcript for session {session_id}")
        return None
    payload = {
        "session_id": session_id,
        "cwd": cwd,
        "transcript_path": str(transcript),
    }
    try:
        device = read_device_name()
        capture_session(payload, device)
        # Mark regardless of push success: the breadcrumb is now in raw/ (or
        # buffered for the next drain), so the Stop hook should not re-write it.
        mark_flushed(flushed_sessions_path(), session_id)
        return session_id
    except Exception as exc:
        log_error(f"consolidate flush failed: {exc!r}")
        return None


def _parse_date(name: str) -> date | None:
    try:
        return datetime.strptime(name, "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_pending_dates(
    repo: Path,
    today: date,
    lookback_days: int = LOOKBACK_DAYS,
) -> list[str]:
    """Dates that still need consolidating, scanning raw/ within a bounded
    lookback. A date is pending when it is today/yesterday (always refreshed,
    matching the nightly window) OR a device worked that date but has no
    matching digest (gap backfill)."""
    raw_root = repo / "raw"
    digests_root = repo / "digests"
    rolling = {today.isoformat(), (today - timedelta(days=1)).isoformat()}
    oldest = today - timedelta(days=lookback_days)
    pending: set[str] = set()
    if raw_root.exists():
        for device_dir in raw_root.iterdir():
            if not device_dir.is_dir():
                continue
            for date_dir in device_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                d = _parse_date(date_dir.name)
                # Require a canonical zero-padded name, so a hand-edited dir like
                # "2026-6-7" can't desync the digest lookup below from the real
                # digests/2026-06-07/ path. Producers always write canonical names.
                if d is None or d.isoformat() != date_dir.name:
                    continue
                if d < oldest or d > today:
                    continue
                if not any(date_dir.glob("*.json")):
                    continue  # device has no real session that date
                date_str = date_dir.name
                if date_str in rolling:
                    pending.add(date_str)
                    continue
                digest = digests_root / date_str / f"{device_dir.name}.md"
                if not digest.exists():
                    pending.add(date_str)
    return sorted(pending)


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def plan(repo: Path, force_date: str | None = None) -> dict:
    """Flush the live session, pull, verify unlocked, and compute the plan."""
    flushed = flush_current_session()
    pull_ok = pull_journal(repo)
    if not is_repo_unlocked(repo):
        return {
            "ok": False,
            "error": "locked",
            "message": (
                f"{repo} is git-crypt locked. Run: git-crypt unlock "
                "~/.claude/journal/git-crypt.key"
            ),
        }
    if force_date:
        if _parse_date(force_date) is None:
            return {"ok": False, "error": "bad-date", "message": f"not a date: {force_date}"}
        dates = [force_date]
    else:
        dates = compute_pending_dates(repo, _today_utc())
    return {
        "ok": True,
        "repo": str(repo),
        "routine": str(repo / "consolidator" / "ROUTINE.md"),
        "dates": dates,
        "pull_ok": pull_ok,
        "flushed_session": flushed,
    }


def _commit_and_push(repo: Path, paths: list[str], msg: str) -> bool:
    add = _run_git(["git", "add", "--", *paths], cwd=repo)
    if add.returncode != 0:
        return False
    commit = _run_git(["git", "commit", "-m", msg], cwd=repo)
    if commit.returncode != 0:
        return False
    # On a rejected push, rebase onto the remote and retry, with 1/4/16s backoff
    # (matching ROUTINE.md §7). No trailing sleep after the final attempt.
    delays = [1, 4, 16]
    for attempt in range(len(delays) + 1):
        _run_git(["git", "pull", "--rebase", "--autostash", "--quiet"], cwd=repo)
        push = _run_git(["git", "push"], cwd=repo)
        if push.returncode == 0:
            return True
        if attempt < len(delays):
            time.sleep(delays[attempt])
    return False


def finalize(repo: Path) -> dict:
    """Stage the derived dirs, skip-if-empty, commit and push."""
    existing = [p for p in DERIVED_PATHS if (repo / p).exists()]
    if not existing:
        return {"ok": True, "changed": False, "message": "nothing to consolidate"}
    add = _run_git(["git", "add", "--", *existing], cwd=repo)
    if add.returncode != 0:
        return {"ok": False, "changed": False, "message": "git add failed"}
    # Check the index, not the working tree, so git-crypt smudge artefacts
    # don't trigger an empty commit.
    diff = _run_git(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if diff.returncode == 0:
        return {"ok": True, "changed": False, "message": "nothing to consolidate"}
    today = _today_utc().isoformat()
    msg = f"consolidate (on-demand): {today}"
    pushed = _commit_and_push(repo, existing, msg)
    return {"ok": pushed, "changed": True, "pushed": pushed, "message": msg}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(json.dumps({"ok": False, "error": "usage", "message": "plan|finalize"}))
        return 2
    cmd, rest = argv[0], argv[1:]
    repo = journal_repo_path()
    if cmd == "plan":
        force_date = rest[0] if rest else None
        result = plan(repo, force_date=force_date)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if cmd == "finalize":
        result = finalize(repo)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    print(json.dumps({"ok": False, "error": "unknown", "message": cmd}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
