"""First-time per-device setup for the journal pipeline.

Run once per device:

    scripts/init-journal-device.sh <device-name>

What it does:
- Clones your claude-journal data repo (CLAUDE_JOURNAL_REPO_URL) if missing.
- Records the device name to ~/.claude/journal/device-name.
- Attempts a git-crypt unlock of the data repo.

When the hooks are installed via the Claude Code plugin, that is all the
setup needed — the plugin registers the Stop/SessionStart hooks and the
`journal` skill declaratively. For a manual (non-plugin) install, pass
`--register-hooks` to additionally:
- Symlink the project's hook entrypoints into ~/.claude/hooks/.
- Symlink the `journal` slash-command skill into ~/.claude/skills/journal/.
- Register the hooks under Stop and SessionStart in ~/.claude/settings.json
  (idempotent — safe to re-run).

Do NOT pass `--register-hooks` if you installed the plugin, or breadcrumbs
will be pushed twice per session.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from tools.journal.autoupdate import enable_marketplace_autoupdate


def _hook_command(python_bin: Path, hook_path: Path) -> str:
    """Compose the shell command Claude Code will run for a hook.

    Uses an explicit python interpreter so the hook isn't required to be
    executable or have a shebang, and so it always runs against the project's
    venv. Both paths are shell-quoted — Claude Code runs the command through
    a shell, so a checkout under a directory with spaces would otherwise
    split into a broken command."""
    return f"{shlex.quote(str(python_bin))} {shlex.quote(str(hook_path))}"


def register_hooks_in_settings(
    *,
    settings_path: Path,
    on_stop_command: str,
    on_start_command: str,
) -> None:
    """Insert the journal hooks into Claude Code's settings.json idempotently.

    Preserves any unrelated content (other settings keys, other hooks).
    Refuses (without touching the file) when settings.json is invalid JSON,
    and writes via a same-directory temp file + os.replace so a crash
    mid-write can never leave a truncated settings.json behind.
    """
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"{settings_path} is not valid JSON ({exc}) — refusing to "
                f"overwrite it. Fix the file and re-run."
            )
    else:
        data = {}
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    hooks = data.setdefault("hooks", {})
    for event, command in (("Stop", on_stop_command), ("SessionStart", on_start_command)):
        groups = hooks.setdefault(event, [])
        if not groups:
            groups.append({"hooks": []})
        existing_cmds = {h.get("command") for g in groups for h in g.get("hooks", [])}
        if command in existing_cmds:
            continue
        groups[0].setdefault("hooks", []).append(
            {"type": "command", "command": command}
        )

    tmp = settings_path.parent / (settings_path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, settings_path)


def _ensure_journal_clone(repo_url: str, target: Path) -> None:
    if target.exists() and (target / ".git").exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", repo_url, str(target)], check=True)


def attempt_unlock(journal_path: Path, keyfile: Path) -> str:
    """Try to unlock the journal repo with git-crypt. Returns a status
    string the caller can print verbatim. Never raises."""
    if not keyfile.exists():
        return (
            f"WARNING: keyfile not found at {keyfile}. claude-journal is "
            f"locked. Transfer the keyfile from your password manager and "
            f"run: git-crypt unlock {keyfile}"
        )
    result = subprocess.run(
        ["git-crypt", "unlock", str(keyfile)],
        cwd=str(journal_path),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return "claude-journal unlocked."
    return (
        f"WARNING: git-crypt unlock failed (exit {result.returncode}): "
        f"{result.stderr.strip() or result.stdout.strip()}"
    )


def _write_device_name(device: str) -> None:
    p = Path.home() / ".claude" / "journal" / "device-name"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(device + "\n")


def _confirm_autoupdate() -> bool:
    """Offer plugin auto-update with a default of yes. Prompt only when stdin
    is interactive; default yes when run non-interactively (e.g. driven by
    Claude) so it never blocks waiting on input."""
    try:
        if sys.stdin.isatty():
            ans = input(
                "[init] Enable plugin auto-update for claude-journal-tools so new "
                "releases reach this device automatically? [Y/n] "
            ).strip().lower()
            return ans in ("", "y", "yes")
    except (EOFError, OSError):
        pass
    return True


def _maybe_enable_autoupdate(no_autoupdate: bool) -> None:
    """Per-device step: offer to enable plugin marketplace auto-update so this
    device picks up new releases without a manual update."""
    if no_autoupdate:
        print("[init] left plugin auto-update unchanged (--no-autoupdate).")
        return
    if not _confirm_autoupdate():
        print("[init] left plugin auto-update unchanged.")
        return
    _, message = enable_marketplace_autoupdate()
    print(f"[init] {message}")


def _symlink(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # is_symlink first: a symlink (even to a directory, even dangling) is
    # ours to replace. A REAL directory is user content — refuse rather than
    # delete it (matching bootstrap's refuse-to-clobber convention).
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        raise SystemExit(
            f"{dst} is a real directory, not a symlink — refusing to replace "
            f"it. Move it aside and re-run."
        )
    dst.symlink_to(src)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize this device for the journal pipeline."
    )
    parser.add_argument(
        "device",
        help="Stable name for this device (e.g., laptop, workstation).",
    )
    parser.add_argument(
        "--repo-url",
        default=os.environ.get("CLAUDE_JOURNAL_REPO_URL"),
        help="Your private claude-journal data-repo git URL. Defaults to "
        "the CLAUDE_JOURNAL_REPO_URL environment variable.",
    )
    parser.add_argument(
        "--journal-path",
        default=os.environ.get(
            "CLAUDE_JOURNAL_PATH", str(Path.home() / "claude-journal")
        ),
        help="Local path for the claude-journal clone.",
    )
    parser.add_argument(
        "--register-hooks",
        action="store_true",
        help="Manual (non-plugin) install: symlink hook entrypoints and the "
        "journal skill into ~/.claude/ and register them in settings.json. "
        "Do NOT use this if you installed the Claude Code plugin.",
    )
    parser.add_argument(
        "--no-autoupdate",
        action="store_true",
        help="Don't offer/enable plugin marketplace auto-update for this device.",
    )
    args = parser.parse_args(argv)

    if not args.repo_url:
        parser.error(
            "no data-repo URL given. Set CLAUDE_JOURNAL_REPO_URL to your "
            "private claude-journal clone URL, or pass --repo-url. This tool "
            "ships no default repo (see SECURITY.md)."
        )

    project_root = Path(__file__).resolve().parents[2]
    on_stop_src = project_root / "tools" / "journal" / "hooks" / "on_stop.py"
    on_start_src = project_root / "tools" / "journal" / "hooks" / "on_start.py"
    on_stop_dst = Path.home() / ".claude" / "hooks" / "journal-on-stop.py"
    on_start_dst = Path.home() / ".claude" / "hooks" / "journal-on-start.py"
    venv_python = project_root / "venv" / "bin" / "python"

    journal_skill_src = project_root / "skills" / "journal"
    journal_skill_dst = Path.home() / ".claude" / "skills" / "journal"

    _ensure_journal_clone(args.repo_url, Path(args.journal_path))
    keyfile = Path.home() / ".claude" / "journal" / "git-crypt.key"
    print(f"[init] {attempt_unlock(Path(args.journal_path), keyfile)}")
    _write_device_name(args.device)

    if args.register_hooks:
        _symlink(on_stop_src, on_stop_dst)
        _symlink(on_start_src, on_start_dst)
        if journal_skill_src.exists():
            _symlink(journal_skill_src, journal_skill_dst)
        register_hooks_in_settings(
            settings_path=Path.home() / ".claude" / "settings.json",
            on_stop_command=_hook_command(venv_python, on_stop_dst),
            on_start_command=_hook_command(venv_python, on_start_dst),
        )
        print("[init] registered hooks + skill (manual mode).")
    else:
        print(
            "[init] skipping hook registration — the Claude Code plugin "
            "provides them. Re-run with --register-hooks for a manual install."
        )

    _maybe_enable_autoupdate(args.no_autoupdate)

    print(f"journal device '{args.device}' initialized.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
