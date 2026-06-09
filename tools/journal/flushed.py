"""Ledger of session ids already captured on-demand by `/journal consolidate`.

The Stop hook consults this so it never re-writes a session the consolidate
flush already pushed (the user asked that the writing not happen twice).
Device-local, one session id per line.
"""
from __future__ import annotations

from pathlib import Path


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def read_flushed(path: Path) -> set[str]:
    return set(_lines(path))


def is_flushed(path: Path, session_id: str) -> bool:
    return bool(session_id) and session_id in read_flushed(path)


def mark_flushed(path: Path, session_id: str, *, keep_last: int = 500) -> None:
    """Record a session id as flushed. No-op if already present. Trims the
    file to the last `keep_last` ids so it cannot grow without bound."""
    if not session_id:
        return
    existing = _lines(path)
    if session_id in existing:
        return
    existing.append(session_id)
    if len(existing) > keep_last:
        existing = existing[-keep_last:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(existing) + "\n")
