"""First-time creation of a brand-new claude-journal *data* repo.

This is the zero-to-running step a stranger needs before any device can push
breadcrumbs. It is separate from `init_device.py` (which provisions a device
against an *existing* data repo).

What it does, idempotently:
- Creates the local repo skeleton (raw/ digests/ memories/ skills/
  proposals/ state/ consolidator/).
- Initializes git-crypt and writes a `.gitattributes` whose encrypted
  directories exactly match `encryption.ENCRYPTED_DIRS` (consolidator/ stays
  plaintext so the routine prompt is readable from a fresh checkout).
- Generates a git-crypt key, exports it to ~/.claude/journal/git-crypt.key,
  and HALTS to make you back it up — losing this key makes every transcript,
  memory, and proposal in the repo permanently unreadable.
- Seeds a generic consolidator/ROUTINE.md.
- Optionally creates the private GitHub repo via `gh` and pushes.

Creating the cloud `/schedule` routine is deliberately left as a guided
manual step (see README) — it needs your key in a cloud env and should be a
conscious action, not a side effect of setup.
"""
from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

from tools.journal.encryption import ENCRYPTED_DIRS

# consolidator/ is intentionally NOT encrypted (the routine must read its own
# prompt from a fresh cloud checkout before it has the key applied).
PLAINTEXT_DIRS = ("consolidator",)
SKELETON_DIRS = ENCRYPTED_DIRS + PLAINTEXT_DIRS

KEYFILE = Path.home() / ".claude" / "journal" / "git-crypt.key"


def gitattributes_content(encrypted_dirs: tuple[str, ...] = ENCRYPTED_DIRS) -> str:
    """`.gitattributes` marking each encrypted directory for git-crypt.

    Kept in lockstep with `encryption.ENCRYPTED_DIRS` so the lock-detection
    logic and the at-rest encryption never disagree."""
    lines = [
        f"{d}/** filter=git-crypt diff=git-crypt" for d in encrypted_dirs
    ]
    return "\n".join(lines) + "\n"


def routine_template_path() -> Path:
    return Path(__file__).resolve().parent / "templates" / "ROUTINE.md"


def read_routine_template() -> str:
    return routine_template_path().read_text(encoding="utf-8")


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _require_tools(need_gh: bool) -> None:
    import shutil

    missing = [t for t in ("git", "git-crypt") if shutil.which(t) is None]
    if need_gh and shutil.which("gh") is None:
        missing.append("gh")
    if missing:
        raise SystemExit(
            f"missing required tool(s): {', '.join(missing)}. Install them "
            f"first (see README)."
        )


def _git_identity_configured() -> bool:
    """True iff git resolves both user.name and user.email to non-empty values.

    Probed from a throwaway non-repo directory so we see exactly the global +
    system (+ env) identity a freshly-created repo's first commit will inherit —
    never some unrelated repo's local config that happens to be the cwd."""
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        for key in ("user.name", "user.email"):
            r = subprocess.run(
                ["git", "config", "--get", key],
                cwd=scratch,
                capture_output=True,
                text=True,
            )
            if r.returncode != 0 or not r.stdout.strip():
                return False
    return True


def _require_git_identity() -> None:
    """Fail fast (before any mutation) if git has no commit identity.

    Otherwise the init commit aborts with 'empty ident name' on fresh
    machines/VMs/containers — *after* the repo, skeleton, git-crypt state and
    the exported key already exist — leaving the user wedged. The journal-setup
    skill sets this interactively; here we only validate."""
    if not _git_identity_configured():
        raise SystemExit(
            "git has no commit identity configured — the init commit would "
            "fail and leave a half-initialized repo behind. Set it first:\n"
            '  git config --global user.name "Your Name"\n'
            '  git config --global user.email "you@example.com"\n'
            "(or run /claude-journal:journal-setup, which does this for you)."
        )


def _require_gh_auth() -> None:
    """Fail fast if `gh` is installed but not logged in, so remote creation
    doesn't blow up deep inside `gh repo create` after the local repo and key
    already exist."""
    r = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise SystemExit(
            "gh is installed but not authenticated — `gh repo create` would "
            "fail. Run `gh auth login` first (or run "
            "/claude-journal:journal-setup, which prompts you to sign in)."
        )


def _write_skeleton(repo: Path) -> None:
    (repo / ".gitattributes").write_text(gitattributes_content())
    for d in SKELETON_DIRS:
        (repo / d).mkdir(parents=True, exist_ok=True)
        # encrypted dirs need a tracked placeholder so the dir survives a
        # clone; a non-empty line ensures git-crypt lock-detection has a file
        # to sample.
        keep = repo / d / ".gitkeep"
        if not keep.exists():
            keep.write_text("# placeholder so this directory is tracked\n")
    routine = repo / "consolidator" / "ROUTINE.md"
    if not routine.exists():
        routine.write_text(read_routine_template(), encoding="utf-8")
    readme = repo / "README.md"
    if not readme.exists():
        readme.write_text(
            "# claude-journal (data repo)\n\n"
            "Private, git-crypt-encrypted store for the claude-journal "
            "pipeline. Created by `journal-bootstrap`. Do not make this "
            "repository public.\n"
        )
    changelog = repo / "CHANGELOG.md"
    if not changelog.exists():
        changelog.write_text("# Changelog\n\n")


def _key_backup_gate(*, assume_backed_up: bool) -> None:
    """Print the git-crypt key and force the user to acknowledge they've saved
    it before we create any remote. Until this returns, nothing has been
    pushed, so aborting here is safe."""
    key_b64 = base64.b64encode(KEYFILE.read_bytes()).decode("ascii")
    print("\n" + "=" * 70)
    print("  GIT-CRYPT KEY — SAVE THIS NOW (password manager).")
    print("  If you lose it, every transcript/memory/proposal in this repo")
    print("  becomes permanently unreadable and no new device can join.")
    print("=" * 70)
    print(f"\n  keyfile : {KEYFILE}")
    print(f"  base64  : {key_b64}\n")
    if assume_backed_up:
        print("[--key-backed-up given] continuing without prompt.\n")
        return
    if not sys.stdin.isatty():
        raise SystemExit(
            "non-interactive run: back up the key above, then re-run with "
            "--key-backed-up to proceed to remote creation. The local repo "
            "is already initialized; re-running is safe."
        )
    resp = input("Type 'saved' once the key is backed up: ").strip().lower()
    if resp != "saved":
        raise SystemExit("aborted before creating any remote. Re-run when ready.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create and initialize a new private claude-journal data repo."
    )
    parser.add_argument(
        "--journal-path",
        default=os.environ.get(
            "CLAUDE_JOURNAL_PATH", str(Path.home() / "claude-journal")
        ),
        help="Local path for the new data repo (default ~/claude-journal).",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="GitHub repo to create as the remote, e.g. <you>/claude-journal. "
        "Omit (or use --no-remote) to initialize locally only.",
    )
    parser.add_argument(
        "--no-remote",
        action="store_true",
        help="Initialize the repo locally only; skip GitHub creation/push.",
    )
    parser.add_argument(
        "--key-backed-up",
        action="store_true",
        help="Skip the interactive key-backup prompt (for automation). Only "
        "pass this once you have actually saved the printed key.",
    )
    args = parser.parse_args(argv)

    repo = Path(args.journal_path)
    need_remote = bool(args.repo) and not args.no_remote
    if args.repo and args.no_remote:
        parser.error("--repo and --no-remote are mutually exclusive.")

    # Validate every precondition BEFORE touching the filesystem, so a missing
    # tool / identity / login or a pre-existing key can never leave a
    # half-initialized repo and an orphaned git-crypt key behind.
    if is_git_repo(repo):
        raise SystemExit(
            f"{repo} is already a git repo — refusing to re-bootstrap. Delete "
            f"it or pick another --journal-path if you really want a fresh one."
        )
    if KEYFILE.exists():
        raise SystemExit(
            f"{KEYFILE} already exists — refusing to overwrite an existing "
            f"key. Move it aside if this is genuinely a new repo."
        )
    _require_tools(need_gh=need_remote)
    _require_git_identity()
    if need_remote:
        _require_gh_auth()

    repo.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-b", "main"], cwd=repo)
    _write_skeleton(repo)
    _run(["git-crypt", "init"], cwd=repo)

    KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(KEYFILE.parent, 0o700)
    _run(["git-crypt", "export-key", str(KEYFILE)], cwd=repo)
    os.chmod(KEYFILE, 0o600)

    _run(["git", "add", "-A"], cwd=repo)
    _run(["git", "commit", "-m", "init: claude-journal data repo skeleton"], cwd=repo)

    _key_backup_gate(assume_backed_up=args.key_backed_up)

    if need_remote:
        _run(
            [
                "gh", "repo", "create", args.repo,
                "--private", "--source", str(repo),
                "--remote", "origin", "--push",
            ],
            cwd=repo,
        )
        print(f"\ncreated private repo {args.repo} and pushed.")
    else:
        print("\nlocal-only init complete. Add a private remote and push when ready.")

    print(
        "\nNext steps:\n"
        "  1. set CLAUDE_JOURNAL_REPO_URL to this repo's URL and run\n"
        "     tools/journal/init_device.py <device-name> on each device.\n"
        "  2. once devices are set up, create the nightly cloud routine with\n"
        "     /claude-journal:journal-schedule (once per account)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
