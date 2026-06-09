"""On-demand recall over the consolidated journal for `/journal recall`.

Reads distilled outputs only — `digests/` and `memories/` — never `raw/` (the
golden rule from docs/agents.md). The mechanical work (pull, unlock check,
date/device enumeration, gap detection, memory listing) lives here; resolving a
natural-language time phrase to dates and synthesizing an answer are the current
session's Claude.

Subcommands
-----------
dates <YYYY-MM-DD>...   Inventory digests for the given dates: which device
                        digests exist, which devices have raw/ but no digest
                        (a gap the caller can offer to consolidate), and which
                        dates captured nothing.
memories [project]      Inventory memory files (+ MEMORY.md indexes), all
                        projects or one project-key.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Self-locate the project root so `tools.journal.X` imports work regardless of
# how Claude Code invokes this script (no PYTHONPATH or cwd assumed).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.journal.encryption import is_repo_unlocked
from tools.journal.paths import journal_repo_path
from tools.journal.pull import pull_journal


def _is_canonical_date(name: str) -> bool:
    """True iff `name` is a real, canonical zero-padded YYYY-MM-DD."""
    try:
        return datetime.strptime(name, "%Y-%m-%d").date().isoformat() == name
    except ValueError:
        return False


def inventory_dates(repo: Path, dates: list) -> dict:
    """For each date, report which device digests exist, which devices have
    raw/ but no digest, and a status. Reads digests/ and raw/ directory names
    only (never raw/ file contents)."""
    digests_root = repo / "digests"
    raw_root = repo / "raw"
    per_date: dict = {}
    for date in dates:
        digest_files = []
        ddir = digests_root / date
        if ddir.exists():
            digest_files = [str(f) for f in sorted(ddir.glob("*.md"))]
        digested_devices = {Path(p).stem for p in digest_files}

        raw_devices = []
        if raw_root.exists():
            for dev in sorted(raw_root.iterdir()):
                if dev.is_dir() and (dev / date).is_dir() and any((dev / date).glob("*.json")):
                    raw_devices.append(dev.name)
        missing = [d for d in raw_devices if d not in digested_devices]

        if digest_files and not missing:
            status = "ok"
        elif raw_devices and not digest_files:
            status = "gap"
        elif missing:
            status = "partial"
        else:
            status = "empty"

        per_date[date] = {
            "digests": digest_files,
            "raw_devices": raw_devices,
            "missing_digest_devices": missing,
            "status": status,
        }

    gaps = [d for d, v in per_date.items() if v["status"] in ("gap", "partial")]
    empty = [d for d, v in per_date.items() if v["status"] == "empty"]
    return {"dates": per_date, "gaps": gaps, "empty": empty}


def inventory_memories(repo: Path, project: str = None) -> dict:
    """List memory files (+ MEMORY.md) per project-key, optionally filtered to
    one project."""
    mem_root = repo / "memories"
    projects: dict = {}
    if mem_root.exists():
        for proj_dir in sorted(mem_root.iterdir()):
            if not proj_dir.is_dir():
                continue
            if project and proj_dir.name != project:
                continue
            index = proj_dir / "MEMORY.md"
            files = [str(f) for f in sorted(proj_dir.glob("*.md")) if f.name != "MEMORY.md"]
            projects[proj_dir.name] = {
                "index": str(index) if index.exists() else None,
                "files": files,
            }
    return {"projects": projects}


def plan(repo: Path, mode: str, args: list) -> dict:
    """Pull, assert the repo is unlocked, then build the requested inventory."""
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
    if mode == "dates":
        bad = [d for d in args if not _is_canonical_date(d)]
        if not args:
            return {"ok": False, "error": "usage", "message": "dates needs at least one YYYY-MM-DD"}
        if bad:
            return {"ok": False, "error": "bad-date", "message": f"not YYYY-MM-DD: {bad}"}
        return {"ok": True, "mode": "dates", "repo": str(repo), "pull_ok": pull_ok, **inventory_dates(repo, args)}
    if mode == "memories":
        project = args[0] if args else None
        return {"ok": True, "mode": "memories", "repo": str(repo), "pull_ok": pull_ok, **inventory_memories(repo, project)}
    return {"ok": False, "error": "usage", "message": "dates|memories"}


def main(argv: list = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(json.dumps({"ok": False, "error": "usage", "message": "dates|memories"}))
        return 2
    mode, rest = argv[0], argv[1:]
    if mode not in ("dates", "memories"):
        print(json.dumps({"ok": False, "error": "unknown", "message": mode}))
        return 2
    result = plan(journal_repo_path(), mode, rest)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
