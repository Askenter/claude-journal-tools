import io
import json
from unittest.mock import MagicMock

from tools.journal.hooks import on_stop


def _stdin(monkeypatch, payload):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))


def test_on_stop_captures_session(monkeypatch, tmp_path):
    fake_capture = MagicMock(return_value=True)
    flushed_file = tmp_path / "flushed"
    monkeypatch.setattr("tools.journal.hooks.on_stop.capture_session", fake_capture)
    monkeypatch.setattr("tools.journal.hooks.on_stop.read_device_name", lambda: "laptop")
    monkeypatch.setattr("tools.journal.hooks.on_stop.flushed_sessions_path", lambda: flushed_file)
    _stdin(monkeypatch, {"session_id": "sess-1", "cwd": "/home/you/myproject", "transcript_path": "/tmp/t.jsonl"})

    rc = on_stop.main()

    assert rc == 0
    fake_capture.assert_called_once()
    payload, device = fake_capture.call_args.args
    assert payload["session_id"] == "sess-1"
    assert device == "laptop"


def test_on_stop_skips_already_flushed_session(monkeypatch, tmp_path):
    """If `/journal consolidate` already flushed this session, the Stop hook
    must NOT write it again."""
    flushed_file = tmp_path / "flushed"
    flushed_file.write_text("sess-1\n")
    fake_capture = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.hooks.on_stop.capture_session", fake_capture)
    monkeypatch.setattr("tools.journal.hooks.on_stop.read_device_name", lambda: "laptop")
    monkeypatch.setattr("tools.journal.hooks.on_stop.flushed_sessions_path", lambda: flushed_file)
    _stdin(monkeypatch, {"session_id": "sess-1", "cwd": "/home/you/myproject", "transcript_path": "/tmp/t.jsonl"})

    rc = on_stop.main()

    assert rc == 0
    fake_capture.assert_not_called()


def test_on_stop_captures_when_a_different_session_was_flushed(monkeypatch, tmp_path):
    flushed_file = tmp_path / "flushed"
    flushed_file.write_text("some-other-session\n")
    fake_capture = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.hooks.on_stop.capture_session", fake_capture)
    monkeypatch.setattr("tools.journal.hooks.on_stop.read_device_name", lambda: "laptop")
    monkeypatch.setattr("tools.journal.hooks.on_stop.flushed_sessions_path", lambda: flushed_file)
    _stdin(monkeypatch, {"session_id": "sess-1", "cwd": "/home/you/myproject", "transcript_path": "/tmp/t.jsonl"})

    on_stop.main()

    fake_capture.assert_called_once()


def test_on_stop_swallows_invalid_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert on_stop.main() == 0


def test_on_stop_swallows_missing_device_name(monkeypatch, tmp_path):
    missing_dev_file = tmp_path / "missing-device-name"
    monkeypatch.setattr("tools.journal.paths.device_name_path", lambda: missing_dev_file)
    _stdin(monkeypatch, {"session_id": "sess-3", "transcript_path": "/tmp/t.jsonl", "cwd": "/home/you/myproject"})
    # read_device_name raises RuntimeError; main must swallow.
    assert on_stop.main() == 0
