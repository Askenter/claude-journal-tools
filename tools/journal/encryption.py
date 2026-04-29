"""Detect whether a journal repo is unlocked (decrypted on disk).

Files encrypted by git-crypt have a fixed 9-byte magic prefix
b"\\x00GITCRYPT". A repo is "unlocked" iff either no encryption is
configured (no filter=git-crypt in .gitattributes), or every file in an
encrypted directory we sample lacks that prefix. We only sample files
under the directories declared encrypted; other repo content (e.g.
consolidator/) is ignored even if it happens to start with the magic.
"""
from __future__ import annotations

from pathlib import Path

GITCRYPT_MAGIC = b"\x00GITCRYPT"
ENCRYPTED_DIRS = ("raw", "digests", "memories", "skills", "proposals", "state")


def is_repo_unlocked(repo: Path) -> bool:
    gitattributes = repo / ".gitattributes"
    if not gitattributes.exists() or "filter=git-crypt" not in gitattributes.read_text():
        return True

    saw_any_file = False
    for d in ENCRYPTED_DIRS:
        directory = repo / d
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            saw_any_file = True
            with path.open("rb") as fh:
                head = fh.read(len(GITCRYPT_MAGIC))
            if head != GITCRYPT_MAGIC:
                return True

    # Encryption configured AND every sampled file starts with the magic
    # prefix -> repo is locked. If we saw no files at all, treat as
    # unlocked (nothing to decrypt yet).
    return not saw_any_file
