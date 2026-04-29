from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)


def _safe_path_segment(value: str) -> str:
    """Strip path-traversal characters from a string before using it as a
    filesystem path segment. Defensive — breadcrumb fields are not generally
    attacker-controlled, but session_id comes from the Stop hook payload."""
    return value.replace("/", "_").replace("\\", "_").replace("..", "__")


def _drain_date_for(breadcrumb: dict, fallback: str) -> str:
    """Derive the YYYY-MM-DD directory bucket from a breadcrumb's own
    started_at, so backlogged breadcrumbs land on the right date when
    drained on a later day. Falls back to the caller's date when started_at
    is missing or malformed."""
    started = breadcrumb.get("started_at")
    if isinstance(started, str) and len(started) >= 10:
        candidate = started[:10]
        if candidate.count("-") == 2:
            return candidate
    return fallback


def _write_breadcrumb_file(*, breadcrumb: dict, journal_repo: Path, date_str: str) -> Path:
    device = _safe_path_segment(breadcrumb.get("device", "unknown"))
    sid = _safe_path_segment(breadcrumb["session_id"])
    target_dir = journal_repo / "raw" / device / date_str
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{sid}.json"
    target.write_text(json.dumps(breadcrumb, indent=2) + "\n")
    return target


def _write_transcript_file(*, breadcrumb: dict, journal_repo: Path, date_str: str, transcript_text: str) -> Optional[Path]:
    if not transcript_text:
        return None
    device = _safe_path_segment(breadcrumb.get("device", "unknown"))
    sid = _safe_path_segment(breadcrumb["session_id"])
    target_dir = journal_repo / "raw" / device / date_str
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{sid}.transcript.md"
    target.write_text(transcript_text if transcript_text.endswith("\n") else transcript_text + "\n")
    return target


def _git_push(journal_repo: Path, msg: str) -> bool:
    # Stage and commit BEFORE pulling. `git pull --rebase` refuses to run
    # with unstaged changes, and a Stop hook can re-fire for the same
    # session_id (resumed session) and rewrite an already-pushed breadcrumb
    # — leaving raw/ tracked files locally modified would otherwise wedge
    # every future push. Include state/ so the project's CLAUDE.md
    # snapshot lands in the same commit when it changed during the session.
    add = _run_git(["git", "add", "-A", "raw/", "state/"], cwd=journal_repo)
    if add.returncode != 0:
        return False
    status = _run_git(["git", "status", "--porcelain"], cwd=journal_repo)
    if status.stdout.strip():
        commit = _run_git(["git", "commit", "-m", msg], cwd=journal_repo)
        if commit.returncode != 0:
            return False
    pull = _run_git(["git", "pull", "--rebase", "--quiet"], cwd=journal_repo)
    if pull.returncode != 0:
        return False
    push = _run_git(["git", "push"], cwd=journal_repo)
    return push.returncode == 0


def _append_to_buffer(buffer: Path, breadcrumb: dict, transcript_text: str) -> None:
    """Buffer entries store {breadcrumb, transcript} as one JSON object per
    line so the drain step can recover both sides without re-reading the
    original transcript path (which may be gone by drain time)."""
    buffer.parent.mkdir(parents=True, exist_ok=True)
    payload = {"breadcrumb": breadcrumb, "transcript": transcript_text}
    with open(buffer, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _parse_buffer_line(line: str) -> Optional[tuple[dict, str]]:
    """Accept both the v2 wrapper schema and the legacy bare-breadcrumb
    schema so an old buffer drains cleanly after the upgrade."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and "breadcrumb" in obj and isinstance(obj["breadcrumb"], dict):
        return obj["breadcrumb"], obj.get("transcript", "") or ""
    if isinstance(obj, dict) and "session_id" in obj:
        return obj, ""
    return None


def _drain_buffer(*, buffer: Path, journal_repo: Path, date_str: str) -> int:
    """Re-apply buffered entries from a previous offline session.

    Writes each backlogged breadcrumb (and transcript, when present) to
    disk, then attempts a single push. On success: clears the buffer and
    returns the count drained. On failure: leaves the buffer intact.
    """
    if not buffer.exists():
        return 0
    drained = 0
    for line in buffer.read_text().splitlines():
        parsed = _parse_buffer_line(line)
        if parsed is None:
            continue
        bc, transcript_text = parsed
        date_for = _drain_date_for(bc, fallback=date_str)
        _write_breadcrumb_file(breadcrumb=bc, journal_repo=journal_repo, date_str=date_for)
        _write_transcript_file(
            breadcrumb=bc, journal_repo=journal_repo, date_str=date_for,
            transcript_text=transcript_text,
        )
        drained += 1
    if _git_push(journal_repo, f"raw: drain backlog ({drained})"):
        buffer.write_text("")
        return drained
    return 0


def push_breadcrumb(
    *,
    breadcrumb: dict,
    journal_repo: Path,
    buffer_path: Path,
    date_str: str,
    transcript_text: str = "",
) -> bool:
    """Stage the breadcrumb (and the transcript text when provided) and try
    to push them in one commit. On failure, append both to the buffer for
    a later drain attempt."""
    try:
        _drain_buffer(buffer=buffer_path, journal_repo=journal_repo, date_str=date_str)
        _write_breadcrumb_file(
            breadcrumb=breadcrumb,
            journal_repo=journal_repo,
            date_str=date_str,
        )
        _write_transcript_file(
            breadcrumb=breadcrumb,
            journal_repo=journal_repo,
            date_str=date_str,
            transcript_text=transcript_text,
        )
        device = breadcrumb.get("device", "unknown")
        if _git_push(journal_repo, f"raw: {device} {date_str} {breadcrumb['session_id']}"):
            return True
    except Exception:
        pass
    _append_to_buffer(buffer_path, breadcrumb, transcript_text)
    return False
