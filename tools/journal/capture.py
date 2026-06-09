"""Shared session capture: build a breadcrumb + transcript and push to raw/.

Used by both the Stop hook (`hooks/on_stop.py`) and on-demand consolidation
(`consolidate.py`'s flush step), so the capture logic lives in exactly one
place. The Stop hook feeds the real Stop payload; consolidate synthesizes a
Stop-like payload for the live session.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tools.journal.breadcrumb import Breadcrumb
from tools.journal.extract import extract_structural
from tools.journal.paths import buffer_path, journal_repo_path
from tools.journal.push import push_breadcrumb
from tools.journal.state import read_project_claudemd, write_state_claudemd
from tools.journal.transcript import extract_transcript_text


def log_error(message: str) -> None:
    """Append a best-effort line to the journal buffer log. Never raises."""
    try:
        log = Path.home() / ".claude" / "journal-buffer.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {message}\n")
    except Exception:
        pass


def _build_breadcrumb(payload: dict, device: str) -> Breadcrumb:
    structural = extract_structural(
        session_id=payload["session_id"],
        device=device,
        project_dir=payload.get("cwd", str(Path.cwd())),
        transcript_path=Path(payload["transcript_path"]),
    )
    started = structural["started_at"] or datetime.now(timezone.utc)
    ended = structural["ended_at"] or datetime.now(timezone.utc)
    return Breadcrumb(
        session_id=structural["session_id"],
        device=structural["device"],
        project=structural["project"],
        started_at=started,
        ended_at=ended,
        files_touched=structural["files_touched"],
        skills_invoked=structural["skills_invoked"],
        first_prompt=structural["first_prompt"],
    )


def capture_session(payload: dict, device: str) -> bool:
    """Build the breadcrumb + transcript for one session and push to raw/.

    Returns True iff the push succeeded. Transcript extraction and CLAUDE.md
    state capture are best-effort: a failure in either still pushes the
    structural breadcrumb. Mirrors the original Stop-hook behavior exactly.
    """
    bc = _build_breadcrumb(payload, device)
    date_str = bc.started_at.strftime("%Y-%m-%d")
    transcript_text = ""
    try:
        transcript_text = extract_transcript_text(Path(payload["transcript_path"]))
    except Exception as exc:
        log_error(f"transcript extract failed: {exc!r}")
    # Capture the project's CLAUDE.md (if present) into journal state so the
    # routine has source-of-truth for Track 3 edit proposals. Best-effort:
    # any failure here must not block the breadcrumb push below.
    try:
        cwd_str = payload.get("cwd")
        if isinstance(cwd_str, str) and cwd_str:
            content = read_project_claudemd(Path(cwd_str))
            if content is not None:
                write_state_claudemd(
                    journal_repo=journal_repo_path(),
                    project_key=bc.project,
                    content=content,
                )
    except Exception as exc:
        log_error(f"state capture failed: {exc!r}")
    return push_breadcrumb(
        breadcrumb=bc.to_dict(),
        journal_repo=journal_repo_path(),
        buffer_path=buffer_path(),
        date_str=date_str,
        transcript_text=transcript_text,
    )
