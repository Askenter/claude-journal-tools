import os
from pathlib import Path


def journal_repo_path() -> Path:
    """Default location of the claude-journal clone."""
    return Path(os.environ.get("CLAUDE_JOURNAL_PATH", str(Path.home() / "claude-journal")))


def buffer_path() -> Path:
    """Local breadcrumb buffer (offline backlog)."""
    return Path(os.environ.get("CLAUDE_JOURNAL_BUFFER", str(Path.home() / ".claude" / "journal-buffer.jsonl")))


def device_name_path() -> Path:
    """Path to the file storing this device's name."""
    return Path.home() / ".claude" / "journal" / "device-name"


def flushed_sessions_path() -> Path:
    """Session ids already captured on-demand by `/journal consolidate`, so
    the later Stop hook skips re-writing them. Device-local, one id per line."""
    return Path.home() / ".claude" / "journal" / "flushed-sessions"


def read_device_name() -> str:
    p = device_name_path()
    if not p.exists():
        raise RuntimeError(
            f"device name not found at {p}; run scripts/init-journal-device.sh first"
        )
    return p.read_text().strip()
