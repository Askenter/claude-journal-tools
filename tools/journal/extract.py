from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tools.journal.breadcrumb import _FIRST_PROMPT_MAX
from tools.journal.redaction import redact as _redact

_TOOLS_THAT_TOUCH_FILES = {"Edit", "Write", "NotebookEdit"}


def _project_key(project_dir: str) -> str:
    """Slugify an absolute path into the auto-memory key format.

    /home/you/myproject -> -home-you-myproject
    """
    return project_dir.replace("/", "-")


def _safe_parse_ts(ts_raw: object) -> datetime | None:
    """Tolerant ISO8601 parser. Accepts trailing 'Z' for compatibility with
    Python <3.11. Returns None for any malformed input — never raises."""
    if not isinstance(ts_raw, str):
        return None
    try:
        if ts_raw.endswith("Z"):
            ts_raw = ts_raw[:-1] + "+00:00"
        return datetime.fromisoformat(ts_raw)
    except (ValueError, TypeError):
        return None


def extract_structural(
    *,
    session_id: str,
    device: str,
    project_dir: str,
    transcript_path: Path,
) -> dict:
    """Read a Claude Code session transcript and return the structural
    breadcrumb fields. Tolerant of missing/empty/malformed transcripts."""
    files: list[str] = []
    skills: list[str] = []
    first_prompt = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None

    if not transcript_path.exists():
        return _empty(session_id, device, project_dir)

    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = _safe_parse_ts(event.get("timestamp"))
            if ts is not None:
                if started_at is None:
                    started_at = ts
                ended_at = ts

            if event.get("type") == "user" and not first_prompt:
                content = event.get("message", {}).get("content", "")
                if isinstance(content, str):
                    # Redact BEFORE truncating: a key cut at the 200-char
                    # boundary would be too short to match any pattern and
                    # leak a partial secret into the breadcrumb.
                    first_prompt = _redact(content)[:_FIRST_PROMPT_MAX]

            if event.get("type") == "assistant":
                content = event.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    name = block.get("name")
                    inp = block.get("input", {}) or {}
                    if name in _TOOLS_THAT_TOUCH_FILES:
                        path = inp.get("file_path")
                        if path and path not in files:
                            files.append(path)
                    elif name == "Skill":
                        skill = inp.get("skill")
                        if skill and skill not in skills:
                            skills.append(skill)

    return {
        "session_id": session_id,
        "device": device,
        "project": _project_key(project_dir),
        "started_at": started_at,
        "ended_at": ended_at,
        "files_touched": files,
        "skills_invoked": skills,
        "first_prompt": first_prompt,
    }


def _empty(session_id: str, device: str, project_dir: str) -> dict:
    return {
        "session_id": session_id,
        "device": device,
        "project": _project_key(project_dir),
        "started_at": None,
        "ended_at": None,
        "files_touched": [],
        "skills_invoked": [],
        "first_prompt": "",
    }
