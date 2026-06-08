"""Stop hook entrypoint. Invoked by Claude Code at session end.

Reads a JSON payload on stdin, builds a structural breadcrumb plus a
tail-truncated transcript text file, and pushes both to claude-journal.
Always exits 0 so it never blocks the user.

The transcript text is what the central routine uses to extract user/
project/feedback memories. The structural breadcrumb on its own is enough
for digests but not for memory distillation.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Self-locate the project root so `tools.journal.X` imports work regardless of
# how Claude Code invokes this script (no PYTHONPATH or cwd assumed).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.journal.breadcrumb import Breadcrumb
from tools.journal.extract import extract_structural
from tools.journal.paths import (
    buffer_path,
    journal_repo_path,
    read_device_name,
)
from tools.journal.push import push_breadcrumb
from tools.journal.state import read_project_claudemd, write_state_claudemd
from tools.journal.transcript import extract_transcript_text


def _read_payload() -> dict:
    return json.loads(sys.stdin.read())


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
        payload = _read_payload()
        device = read_device_name()
        bc = _build_breadcrumb(payload, device)
        date_str = bc.started_at.strftime("%Y-%m-%d")
        transcript_text = ""
        try:
            transcript_text = extract_transcript_text(Path(payload["transcript_path"]))
        except Exception as exc:
            # Transcript extraction is best-effort: structural breadcrumb still pushes.
            _log_error(f"transcript extract failed: {exc!r}")
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
            _log_error(f"state capture failed: {exc!r}")
        push_breadcrumb(
            breadcrumb=bc.to_dict(),
            journal_repo=journal_repo_path(),
            buffer_path=buffer_path(),
            date_str=date_str,
            transcript_text=transcript_text,
        )
    except Exception as exc:
        _log_error(f"on_stop error: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
