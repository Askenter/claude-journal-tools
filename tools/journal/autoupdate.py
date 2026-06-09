"""Enable plugin marketplace auto-update declaratively in settings.json.

Used by `/journal setup` (Step 7) and per-device init (`init_device.py`) so a
new plugin release reaches every device without a manual update. The mechanism
is Claude Code's documented `extraKnownMarketplaces.<name>.autoUpdate` flag in
settings.json — exactly what the `/plugin` > Marketplaces toggle writes. The
marketplace name and source are read from the live `known_marketplaces.json`
registry so we never hardcode the owner.

Runnable as `python3 "$TOOLS/tools/journal/autoupdate.py"`; importable as
`enable_marketplace_autoupdate(...)`. Pure stdlib, never raises on bad input.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, Tuple

MARKETPLACE_SUFFIX = "/claude-journal-tools"
DEFAULT_MARKETPLACE = "claude-journal-tools"


def _default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _default_known_path() -> Path:
    return Path.home() / ".claude" / "plugins" / "known_marketplaces.json"


def _source_points_at_tools(source: dict) -> bool:
    repo = str(source.get("repo", "")).rstrip("/")
    url = str(source.get("url", "")).rstrip("/")
    return (
        repo.endswith(MARKETPLACE_SUFFIX)
        or url.endswith(MARKETPLACE_SUFFIX)
        or url.endswith(MARKETPLACE_SUFFIX + ".git")
    )


def _find_marketplace(known: dict) -> Optional[Tuple[str, dict]]:
    """Return (name, source) for the journal marketplace registered in
    known_marketplaces.json — the entry whose source repo/url ends in
    /claude-journal-tools. None when it isn't a marketplace (plugin) install."""
    for name, entry in known.items():
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        if isinstance(source, dict) and _source_points_at_tools(source):
            return name, source
    return None


def enable_marketplace_autoupdate(
    *,
    settings_path: Optional[Path] = None,
    known_marketplaces_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Idempotently declare the journal marketplace with `autoUpdate: true` in
    settings.json, preserving every other key. Returns (changed, message).

    Never raises. If the marketplace isn't registered (a manual/symlink install)
    it skips. If settings.json exists but is invalid JSON it is left untouched.
    """
    settings_path = settings_path or _default_settings_path()
    known_path = known_marketplaces_path or _default_known_path()

    # Resolve the registered name + source so the entry merges with — never
    # duplicates — the existing registration.
    found = None
    if known_path.exists():
        try:
            known = json.loads(known_path.read_text())
        except (OSError, json.JSONDecodeError):
            known = {}
        if isinstance(known, dict):
            found = _find_marketplace(known)
    if found is None:
        return (
            False,
            "not a plugin install (no claude-journal-tools marketplace "
            "registered) — updates come from a git pull of your checkout, not "
            "plugin auto-update.",
        )
    name, source = found

    # Load settings, preserving everything; refuse to clobber unreadable JSON.
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (OSError, json.JSONDecodeError):
            return (
                False,
                f"WARNING: {settings_path} is not valid JSON; left untouched. "
                f"Enable auto-update via /plugin > Marketplaces > {name}.",
            )
        if not isinstance(settings, dict):
            return (False, f"WARNING: {settings_path} is not a JSON object; left untouched.")
    else:
        settings = {}

    ekm = settings.get("extraKnownMarketplaces")
    if not isinstance(ekm, dict):
        ekm = {}
    entry = dict(ekm.get(name) or {})
    new_entry = dict(entry)
    if "source" not in new_entry:
        new_entry["source"] = source
    new_entry["autoUpdate"] = True

    if entry == new_entry and entry.get("autoUpdate") is True:
        return (False, f"plugin auto-update already enabled for {name}.")

    ekm[name] = new_entry
    settings["extraKnownMarketplaces"] = ekm
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return (True, f"enabled plugin auto-update for {name} in {settings_path}.")


def main(argv: Optional[list] = None) -> int:
    changed, message = enable_marketplace_autoupdate()
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
