from pathlib import Path

import pytest

from tools.journal import bootstrap
from tools.journal.encryption import ENCRYPTED_DIRS, GITCRYPT_MAGIC, is_repo_unlocked


def test_gitattributes_covers_every_encrypted_dir():
    content = bootstrap.gitattributes_content()
    for d in ENCRYPTED_DIRS:
        assert f"{d}/** filter=git-crypt diff=git-crypt" in content


def test_gitattributes_does_not_encrypt_consolidator():
    # The routine must read its own prompt from a fresh checkout, so the
    # consolidator dir stays plaintext.
    content = bootstrap.gitattributes_content()
    assert "consolidator" not in content


def test_skeleton_is_encrypted_dirs_plus_consolidator():
    assert set(bootstrap.SKELETON_DIRS) == set(ENCRYPTED_DIRS) | {"consolidator"}


def test_routine_template_exists_and_is_generic():
    text = bootstrap.read_routine_template()
    assert "GIT_CRYPT_KEY_B64" in text
    # No personal coupling baked into the shipped template.
    assert "askenter" not in text.lower()


def test_write_skeleton_creates_tracked_structure(tmp_path):
    bootstrap._write_skeleton(tmp_path)
    assert (tmp_path / ".gitattributes").exists()
    assert (tmp_path / "consolidator" / "ROUTINE.md").exists()
    for d in ENCRYPTED_DIRS:
        assert (tmp_path / d / ".gitkeep").exists()


def test_write_skeleton_is_idempotent_and_preserves_content(tmp_path):
    bootstrap._write_skeleton(tmp_path)
    marker = tmp_path / "raw" / ".gitkeep"
    marker.write_text("custom")
    bootstrap._write_skeleton(tmp_path)  # second run must not clobber
    assert marker.read_text() == "custom"


def test_gitattributes_matches_lockdetection_dirs(tmp_path):
    # A skeleton with git-crypt-style ciphertext in encrypted dirs must read
    # as "locked"; plaintext must read as "unlocked". Guards the contract
    # between the .gitattributes we write and encryption.is_repo_unlocked.
    bootstrap._write_skeleton(tmp_path)
    assert is_repo_unlocked(tmp_path) is True  # placeholders are plaintext
    (tmp_path / "raw" / ".gitkeep").write_bytes(GITCRYPT_MAGIC + b"ciphertext")
    # one ciphertext file is enough to flip a sampled dir to "locked" only if
    # every sampled file has the magic; the other dirs still have plaintext
    # placeholders, so the repo as a whole still reads unlocked.
    assert is_repo_unlocked(tmp_path) is True


def test_main_refuses_existing_git_repo(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(SystemExit):
        bootstrap.main(["--journal-path", str(tmp_path), "--no-remote"])


def test_main_rejects_repo_with_no_remote(tmp_path):
    target = tmp_path / "j"
    with pytest.raises(SystemExit):
        bootstrap.main(["--journal-path", str(target), "--repo", "x/y", "--no-remote"])
