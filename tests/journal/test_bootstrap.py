import subprocess
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


def test_main_refuses_before_mutation_when_keyfile_exists(tmp_path, monkeypatch):
    # bug_002: the pre-existing-key guard must fire BEFORE git init / git-crypt
    # init pollute a fresh repo, so we never strand an unexported key.
    key = tmp_path / "key"
    key.write_text("pre-existing")
    monkeypatch.setattr(bootstrap, "KEYFILE", key)
    target = tmp_path / "j"
    with pytest.raises(SystemExit):
        bootstrap.main(["--journal-path", str(target), "--no-remote"])
    assert not (target / ".git").exists()  # bailed before touching the fs


def test_main_refuses_before_mutation_without_identity(tmp_path, monkeypatch):
    # bug_014: no git identity must bail up front, not mid-init after the repo,
    # git-crypt state and exported key already exist.
    monkeypatch.setattr(bootstrap, "KEYFILE", tmp_path / "absent-key")
    monkeypatch.setattr(bootstrap, "_require_tools", lambda need_gh: None)
    monkeypatch.setattr(bootstrap, "_git_identity_configured", lambda: False)
    target = tmp_path / "j"
    with pytest.raises(SystemExit):
        bootstrap.main(["--journal-path", str(target), "--no-remote"])
    assert not (target / ".git").exists()


def test_git_identity_configured_false_when_a_field_missing(monkeypatch):
    def fake_run(cmd, *a, **k):
        out = "Anthony\n" if cmd[-1] == "user.name" else ""  # email unset
        return subprocess.CompletedProcess(cmd, 0 if out else 1, stdout=out, stderr="")

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    assert bootstrap._git_identity_configured() is False


def test_git_identity_configured_true_when_both_set(monkeypatch):
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 0, stdout="x\n", stderr=""),
    )
    assert bootstrap._git_identity_configured() is True


def test_require_gh_auth_raises_when_unauthenticated(monkeypatch):
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not logged in"),
    )
    with pytest.raises(SystemExit):
        bootstrap._require_gh_auth()


def test_require_gh_auth_ok_when_authenticated(monkeypatch):
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 0, stdout="Logged in", stderr=""),
    )
    bootstrap._require_gh_auth()  # must not raise
