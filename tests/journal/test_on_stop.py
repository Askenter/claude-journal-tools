import io
import json
from unittest.mock import MagicMock
from tools.journal.hooks import on_stop


def _arrange(monkeypatch, tmp_path, payload):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type":"user","timestamp":"2026-04-28T09:00:00Z","message":{"content":"Do thing."}}\n'
        '{"type":"assistant","timestamp":"2026-04-28T09:30:00Z","message":{"content":[{"type":"tool_use","name":"Edit","input":{"file_path":"src/api.py"}}]}}\n'
    )
    journal = tmp_path / "claude-journal"
    (journal / "raw").mkdir(parents=True)
    buffer = tmp_path / "journal-buffer.jsonl"
    device_name_file = tmp_path / "device-name"
    device_name_file.write_text("laptop\n")

    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.paths.buffer_path", lambda: buffer)
    monkeypatch.setattr("tools.journal.paths.device_name_path", lambda: device_name_file)

    fake_push = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.hooks.on_stop.push_breadcrumb", fake_push)

    payload["transcript_path"] = str(transcript)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return fake_push


def test_on_stop_pushes_structural_breadcrumb(monkeypatch, tmp_path):
    fake_push = _arrange(
        monkeypatch, tmp_path,
        payload={"session_id": "sess-1", "cwd": "/home/opc/ASEP"},
    )

    rc = on_stop.main()

    assert rc == 0
    fake_push.assert_called_once()
    sent = fake_push.call_args.kwargs["breadcrumb"]
    assert sent["session_id"] == "sess-1"
    assert sent["device"] == "laptop"
    assert sent["project"] == "-home-opc-ASEP"
    assert sent["files_touched"] == ["src/api.py"]
    assert fake_push.call_args.kwargs["date_str"] == "2026-04-28"
    # No LLM-augmented fields in Phase 1.
    assert "session_summary" not in sent
    assert "decisions" not in sent
    assert "facts_learned" not in sent
    assert "open_questions" not in sent


def test_on_stop_writes_project_state_when_claudemd_exists(monkeypatch, tmp_path):
    """When the project has a CLAUDE.md, the Stop hook should snapshot it
    into journal/state/<project>/CLAUDE.md before pushing."""
    project = tmp_path / "ASEP"
    project.mkdir()
    (project / "CLAUDE.md").write_text("# project rules\n")
    journal = tmp_path / "claude-journal"
    (journal / "raw").mkdir(parents=True)
    buffer = tmp_path / "buf.jsonl"
    devname = tmp_path / "device-name"
    devname.write_text("laptop\n")

    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type":"user","timestamp":"2026-04-28T09:00:00Z","message":{"content":"hi"}}\n'
    )

    # Patch the bindings the on_stop module imported, not the source module —
    # `from X import f` creates a fresh local binding immune to source patches.
    monkeypatch.setattr("tools.journal.hooks.on_stop.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.hooks.on_stop.buffer_path", lambda: buffer)
    monkeypatch.setattr("tools.journal.paths.device_name_path", lambda: devname)
    monkeypatch.setattr("tools.journal.hooks.on_stop.read_device_name", lambda: "laptop")
    monkeypatch.setattr("tools.journal.hooks.on_stop.push_breadcrumb", MagicMock(return_value=True))

    payload = {"session_id": "s1", "cwd": str(project), "transcript_path": str(transcript)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    on_stop.main()

    state_files = list((journal / "state").rglob("CLAUDE.md"))
    assert len(state_files) == 1
    assert "project rules" in state_files[0].read_text()


def test_on_stop_skips_state_when_no_claudemd(monkeypatch, tmp_path):
    project = tmp_path / "noclaude"
    project.mkdir()
    journal = tmp_path / "claude-journal"
    (journal / "raw").mkdir(parents=True)
    buffer = tmp_path / "buf.jsonl"
    devname = tmp_path / "device-name"
    devname.write_text("laptop\n")
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("")

    monkeypatch.setattr("tools.journal.hooks.on_stop.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.hooks.on_stop.buffer_path", lambda: buffer)
    monkeypatch.setattr("tools.journal.hooks.on_stop.read_device_name", lambda: "laptop")
    monkeypatch.setattr("tools.journal.hooks.on_stop.push_breadcrumb", MagicMock(return_value=True))

    payload = {"session_id": "s1", "cwd": str(project), "transcript_path": str(transcript)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    on_stop.main()

    assert not (journal / "state").exists() or not list((journal / "state").rglob("CLAUDE.md"))


def test_on_stop_swallows_invalid_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert on_stop.main() == 0


def test_on_stop_swallows_missing_device_name(monkeypatch, tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("")
    missing_dev_file = tmp_path / "missing-device-name"
    monkeypatch.setattr("tools.journal.paths.device_name_path", lambda: missing_dev_file)
    payload = {
        "session_id": "sess-3",
        "transcript_path": str(transcript),
        "cwd": "/home/opc/ASEP",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    # read_device_name raises RuntimeError; main must swallow.
    assert on_stop.main() == 0
