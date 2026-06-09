"""Stop hook entrypoint. Invoked by Claude Code at session end.

Reads a JSON payload on stdin, builds a structural breadcrumb plus a
tail-truncated transcript text file, and pushes both to claude-journal.
Always exits 0 so it never blocks the user.

The capture itself lives in `tools.journal.capture` so the same code path is
shared with on-demand consolidation (`/journal consolidate`). If a session was
already captured on-demand by a consolidate flush, its id is in the flushed
ledger and this hook skips re-writing it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Self-locate the project root so `tools.journal.X` imports work regardless of
# how Claude Code invokes this script (no PYTHONPATH or cwd assumed).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.journal.capture import capture_session, log_error
from tools.journal.flushed import is_flushed
from tools.journal.paths import flushed_sessions_path, read_device_name


def _read_payload() -> dict:
    return json.loads(sys.stdin.read())


def main() -> int:
    try:
        payload = _read_payload()
        device = read_device_name()
        session_id = payload.get("session_id")
        # If `/journal consolidate` already flushed this session on-demand,
        # don't write it a second time — the flush is authoritative.
        if is_flushed(flushed_sessions_path(), session_id):
            return 0
        capture_session(payload, device)
    except Exception as exc:
        log_error(f"on_stop error: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
