import json
import os
import subprocess
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from tools.journal import init_device
from tools.journal.init_device import _hook_command, _symlink, attempt_unlock, register_hooks_in_settings


def test_hook_command_uses_explicit_python():
    cmd = _hook_command(Path("/v/python"), Path("/h/on_stop.py"))
    assert cmd == "/v/python /h/on_stop.py"


def test_hook_command_with_spaces_runs_under_shell(tmp_path):
    """Claude Code runs hook commands through a shell. A checkout under a
    directory with spaces must produce a command that still executes — i.e.
    both paths must be shell-quoted, proven by actually running it."""
    venv_dir = tmp_path / "my venv" / "bin"
    venv_dir.mkdir(parents=True)
    python_link = venv_dir / "python"
    python_link.symlink_to(sys.executable)

    hooks_dir = tmp_path / "my hooks"
    hooks_dir.mkdir()
    marker = tmp_path / "ran.txt"
    hook = hooks_dir / "on stop.py"
    hook.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ok')\n"
    )

    cmd = _hook_command(python_link, hook)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert marker.read_text() == "ok"


def test_register_hooks_refuses_invalid_settings_json(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{not valid json")
    with pytest.raises(SystemExit) as exc:
        register_hooks_in_settings(
            settings_path=settings,
            on_stop_command="/v/python /h/on_stop.py",
            on_start_command="/v/python /h/on_start.py",
        )
    assert "not valid JSON" in str(exc.value)
    # The broken file is left exactly as it was, never clobbered.
    assert settings.read_text() == "{not valid json"


def test_register_hooks_leaves_no_temp_files(tmp_path):
    settings = tmp_path / "settings.json"
    register_hooks_in_settings(
        settings_path=settings,
        on_stop_command="/v/python /h/on_stop.py",
        on_start_command="/v/python /h/on_start.py",
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


def test_symlink_replaces_existing_symlink(tmp_path):
    src_a = tmp_path / "a"
    src_a.mkdir()
    src_b = tmp_path / "b"
    src_b.mkdir()
    dst = tmp_path / "link"
    _symlink(src_a, dst)
    _symlink(src_b, dst)
    assert dst.is_symlink()
    assert os.readlink(dst) == str(src_b)


def test_symlink_refuses_real_directory(tmp_path):
    """A real (user-created) directory at the destination must never be
    silently deleted — refuse with an actionable message instead of the
    bare IsADirectoryError the old unlink raised."""
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "skills" / "journal"
    dst.mkdir(parents=True)
    (dst / "user-content.md").write_text("mine\n")
    with pytest.raises(SystemExit) as exc:
        _symlink(src, dst)
    assert "refusing" in str(exc.value)
    assert (dst / "user-content.md").read_text() == "mine\n"


def test_register_hooks_creates_settings(tmp_path):
    settings = tmp_path / "settings.json"
    stop_cmd = "/v/python /h/on_stop.py"
    start_cmd = "/v/python /h/on_start.py"

    register_hooks_in_settings(
        settings_path=settings,
        on_stop_command=stop_cmd,
        on_start_command=start_cmd,
    )
    data = json.loads(settings.read_text())
    stop_cmds = [h["command"] for h in data["hooks"]["Stop"][0]["hooks"]]
    start_cmds = [h["command"] for h in data["hooks"]["SessionStart"][0]["hooks"]]
    assert stop_cmd in stop_cmds
    assert start_cmd in start_cmds


def test_register_hooks_is_idempotent(tmp_path):
    settings = tmp_path / "settings.json"
    stop_cmd = "/v/python /h/on_stop.py"
    start_cmd = "/v/python /h/on_start.py"

    register_hooks_in_settings(settings_path=settings, on_stop_command=stop_cmd, on_start_command=start_cmd)
    register_hooks_in_settings(settings_path=settings, on_stop_command=stop_cmd, on_start_command=start_cmd)

    data = json.loads(settings.read_text())
    stop_hooks = data["hooks"]["Stop"][0]["hooks"]
    matching = [h for h in stop_hooks if h.get("command") == stop_cmd]
    assert len(matching) == 1


def test_register_hooks_preserves_existing_unrelated(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "theme": "dark",
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "/some/other/hook.sh"}]}]
        }
    }))
    stop_cmd = "/v/python /h/on_stop.py"
    start_cmd = "/v/python /h/on_start.py"
    register_hooks_in_settings(
        settings_path=settings, on_stop_command=stop_cmd, on_start_command=start_cmd
    )

    data = json.loads(settings.read_text())
    assert data["theme"] == "dark"
    cmds = [h["command"] for h in data["hooks"]["Stop"][0]["hooks"]]
    assert "/some/other/hook.sh" in cmds
    assert stop_cmd in cmds


def test_attempt_unlock_warns_when_keyfile_missing(tmp_path):
    journal = tmp_path / "j"
    journal.mkdir()
    keyfile = tmp_path / "no-such-file.key"
    msg = attempt_unlock(journal, keyfile)
    assert "WARNING" in msg
    assert str(keyfile) in msg


def test_attempt_unlock_succeeds_when_subprocess_returns_zero(tmp_path, monkeypatch):
    journal = tmp_path / "j"
    journal.mkdir()
    keyfile = tmp_path / "key"
    keyfile.write_bytes(b"\x00fake-key")

    fake_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr("tools.journal.init_device.subprocess.run", fake_run)

    msg = attempt_unlock(journal, keyfile)
    assert msg == "claude-journal unlocked."
    args, kwargs = fake_run.call_args
    assert args[0] == ["git-crypt", "unlock", str(keyfile)]
    assert kwargs["cwd"] == str(journal)


def test_attempt_unlock_warns_when_git_crypt_fails(tmp_path, monkeypatch):
    journal = tmp_path / "j"
    journal.mkdir()
    keyfile = tmp_path / "key"
    keyfile.write_bytes(b"\x00bad-key")

    fake_run = MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="bad key"))
    monkeypatch.setattr("tools.journal.init_device.subprocess.run", fake_run)

    msg = attempt_unlock(journal, keyfile)
    assert "WARNING" in msg
    assert "bad key" in msg


def test_maybe_enable_autoupdate_enables_by_default(monkeypatch):
    spy = MagicMock(return_value=(True, "enabled"))
    monkeypatch.setattr(init_device, "enable_marketplace_autoupdate", spy)
    monkeypatch.setattr(init_device, "_confirm_autoupdate", lambda: True)
    init_device._maybe_enable_autoupdate(False)
    spy.assert_called_once()


def test_maybe_enable_autoupdate_respects_opt_out(monkeypatch):
    spy = MagicMock(return_value=(True, "enabled"))
    monkeypatch.setattr(init_device, "enable_marketplace_autoupdate", spy)
    init_device._maybe_enable_autoupdate(True)
    spy.assert_not_called()


def test_maybe_enable_autoupdate_skips_when_declined(monkeypatch):
    spy = MagicMock(return_value=(True, "enabled"))
    monkeypatch.setattr(init_device, "enable_marketplace_autoupdate", spy)
    monkeypatch.setattr(init_device, "_confirm_autoupdate", lambda: False)
    init_device._maybe_enable_autoupdate(False)
    spy.assert_not_called()


def test_confirm_autoupdate_defaults_yes_when_non_interactive(monkeypatch):
    monkeypatch.setattr(init_device.sys.stdin, "isatty", lambda: False)
    assert init_device._confirm_autoupdate() is True


def test_register_hooks_creates_session_start_when_only_stop_exists(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "/some/other/hook.sh"}]}]
        }
    }))
    stop_cmd = "/v/python /h/on_stop.py"
    start_cmd = "/v/python /h/on_start.py"
    register_hooks_in_settings(
        settings_path=settings, on_stop_command=stop_cmd, on_start_command=start_cmd
    )

    data = json.loads(settings.read_text())
    start_cmds = [h["command"] for h in data["hooks"]["SessionStart"][0]["hooks"]]
    assert start_cmd in start_cmds
