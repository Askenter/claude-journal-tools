from pathlib import Path

from tools.journal.encryption import is_repo_unlocked


def test_unlocked_when_no_gitattributes(tmp_path: Path):
    # No .gitattributes => no git-crypt configured => trivially unlocked.
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "x.json").write_text('{"k":"v"}')
    assert is_repo_unlocked(tmp_path) is True


def test_unlocked_when_gitattributes_has_no_gitcrypt_filter(tmp_path: Path):
    (tmp_path / ".gitattributes").write_text("*.txt text=auto\n")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "x.json").write_bytes(b"\x00GITCRYPT\x00ciphertext")
    assert is_repo_unlocked(tmp_path) is True


def test_locked_when_encrypted_file_starts_with_gitcrypt_magic(tmp_path: Path):
    (tmp_path / ".gitattributes").write_text("raw/** filter=git-crypt diff=git-crypt\n")
    (tmp_path / "raw").mkdir()
    # First 9 bytes of any git-crypt-encrypted file are b"\x00GITCRYPT".
    (tmp_path / "raw" / "x.json").write_bytes(b"\x00GITCRYPT\x00rest-is-ciphertext")
    assert is_repo_unlocked(tmp_path) is False


def test_unlocked_when_encrypted_dir_has_plaintext(tmp_path: Path):
    (tmp_path / ".gitattributes").write_text("raw/** filter=git-crypt diff=git-crypt\n")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "x.json").write_text('{"k":"v"}\n')
    assert is_repo_unlocked(tmp_path) is True


def test_unlocked_when_encrypted_dirs_are_empty(tmp_path: Path):
    (tmp_path / ".gitattributes").write_text("raw/** filter=git-crypt diff=git-crypt\n")
    assert is_repo_unlocked(tmp_path) is True


def test_unlocked_ignores_non_encrypted_dirs(tmp_path: Path):
    # Even if some other (non-encrypted) file happens to start with the
    # magic bytes, it must not flip the lock detection.
    (tmp_path / ".gitattributes").write_text("raw/** filter=git-crypt diff=git-crypt\n")
    (tmp_path / "consolidator").mkdir()
    (tmp_path / "consolidator" / "weird.bin").write_bytes(b"\x00GITCRYPT\x00")
    assert is_repo_unlocked(tmp_path) is True
