from unittest.mock import MagicMock

from tools.journal import capture


def _arrange(monkeypatch, tmp_path, *, cwd):
    journal = tmp_path / "claude-journal"
    (journal / "raw").mkdir(parents=True)
    buffer = tmp_path / "buf.jsonl"
    monkeypatch.setattr("tools.journal.capture.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.capture.buffer_path", lambda: buffer)
    fake_push = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.capture.push_breadcrumb", fake_push)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type":"user","timestamp":"2026-04-28T09:00:00Z","message":{"content":"Do thing."}}\n'
        '{"type":"assistant","timestamp":"2026-04-28T09:30:00Z","message":{"content":[{"type":"tool_use","name":"Edit","input":{"file_path":"src/api.py"}}]}}\n'
    )
    payload = {"session_id": "sess-1", "cwd": str(cwd), "transcript_path": str(transcript)}
    return journal, fake_push, payload


def test_capture_builds_and_pushes_breadcrumb(monkeypatch, tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
    journal, fake_push, payload = _arrange(monkeypatch, tmp_path, cwd=project)

    ok = capture.capture_session(payload, "laptop")

    assert ok is True
    fake_push.assert_called_once()
    sent = fake_push.call_args.kwargs["breadcrumb"]
    assert sent["session_id"] == "sess-1"
    assert sent["device"] == "laptop"
    assert sent["files_touched"] == ["src/api.py"]
    assert fake_push.call_args.kwargs["date_str"] == "2026-04-28"


def test_capture_snapshots_claudemd_when_present(monkeypatch, tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
    (project / "CLAUDE.md").write_text("# project rules\n")
    journal, _, payload = _arrange(monkeypatch, tmp_path, cwd=project)

    capture.capture_session(payload, "laptop")

    state_files = list((journal / "state").rglob("CLAUDE.md"))
    assert len(state_files) == 1
    assert "project rules" in state_files[0].read_text()


def test_capture_skips_state_when_no_claudemd(monkeypatch, tmp_path):
    project = tmp_path / "noclaude"
    project.mkdir()
    journal, _, payload = _arrange(monkeypatch, tmp_path, cwd=project)

    capture.capture_session(payload, "laptop")

    assert not (journal / "state").exists() or not list((journal / "state").rglob("CLAUDE.md"))


def test_capture_tolerates_missing_transcript(monkeypatch, tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
    journal, fake_push, payload = _arrange(monkeypatch, tmp_path, cwd=project)
    payload["transcript_path"] = str(tmp_path / "does-not-exist.jsonl")

    ok = capture.capture_session(payload, "laptop")

    assert ok is True
    fake_push.assert_called_once()
    # No transcript text, but the structural breadcrumb still pushes.
    assert fake_push.call_args.kwargs["transcript_text"] == ""
