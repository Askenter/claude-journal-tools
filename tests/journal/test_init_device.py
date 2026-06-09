import json
from pathlib import Path
from unittest.mock import MagicMock
from tools.journal import init_device
from tools.journal.init_device import _hook_command, attempt_unlock, register_hooks_in_settings


def test_hook_command_uses_explicit_python():
    cmd = _hook_command(Path("/v/python"), Path("/h/on_stop.py"))
    assert cmd == "/v/python /h/on_stop.py"


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
