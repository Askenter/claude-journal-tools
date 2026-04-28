import json
import subprocess
from pathlib import Path


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


def _git_push(journal_repo: Path, msg: str) -> bool:
    pull = _run_git(["git", "pull", "--rebase", "--quiet"], cwd=journal_repo)
    if pull.returncode != 0:
        return False
    add = _run_git(["git", "add", "raw/"], cwd=journal_repo)
    if add.returncode != 0:
        return False
    status = _run_git(["git", "status", "--porcelain"], cwd=journal_repo)
    if not status.stdout.strip():
        return True
    commit = _run_git(["git", "commit", "-m", msg], cwd=journal_repo)
    if commit.returncode != 0:
        return False
    push = _run_git(["git", "push"], cwd=journal_repo)
    return push.returncode == 0


def _append_to_buffer(buffer: Path, breadcrumb: dict) -> None:
    buffer.parent.mkdir(parents=True, exist_ok=True)
    with open(buffer, "a", encoding="utf-8") as f:
        f.write(json.dumps(breadcrumb) + "\n")


def _drain_buffer(*, buffer: Path, journal_repo: Path, date_str: str) -> int:
    """Re-apply buffered breadcrumbs from a previous offline session.

    Writes each backlogged breadcrumb to disk, then attempts a single push.
    On push success: clears the buffer and returns the count drained.
    On push failure: leaves the buffer intact and returns 0 — the next call
    will retry.
    """
    if not buffer.exists():
        return 0
    drained = 0
    for line in buffer.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            bc = json.loads(line)
        except json.JSONDecodeError:
            continue
        _write_breadcrumb_file(
            breadcrumb=bc,
            journal_repo=journal_repo,
            date_str=_drain_date_for(bc, fallback=date_str),
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
) -> bool:
    """Stage the breadcrumb and try to push. On failure, append to buffer."""
    try:
        _drain_buffer(buffer=buffer_path, journal_repo=journal_repo, date_str=date_str)
        _write_breadcrumb_file(
            breadcrumb=breadcrumb,
            journal_repo=journal_repo,
            date_str=date_str,
        )
        device = breadcrumb.get("device", "unknown")
        if _git_push(journal_repo, f"raw: {device} {date_str} {breadcrumb['session_id']}"):
            return True
    except Exception:
        pass
    _append_to_buffer(buffer_path, breadcrumb)
    return False
