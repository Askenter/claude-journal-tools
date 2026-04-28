import json
from pathlib import Path
from tools.journal.init_device import _hook_command, register_hooks_in_settings


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
