import io
import json
from unittest.mock import MagicMock
from tools.journal.hooks import on_start
from tools.journal import pull as pull_module


def test_on_start_pulls_repo(monkeypatch, tmp_path):
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)

    fake_pull = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", fake_pull)

    payload = {"session_id": "sess-1", "cwd": "/home/opc/ASEP"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = on_start.main()

    assert rc == 0
    fake_pull.assert_called_once()


def test_on_start_swallows_pull_failure(monkeypatch):
    fake_pull = MagicMock(return_value=False)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", fake_pull)
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert on_start.main() == 0


def test_on_start_calls_sync_memories_and_skills(monkeypatch, tmp_path):
    """Phase 3: SessionStart pulls AND mirrors memories/skills to the
    device after pulling."""
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", MagicMock(return_value=True))

    fake_sync_mem = MagicMock(return_value=[])
    fake_sync_skl = MagicMock(return_value=[])
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_memories", fake_sync_mem)
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_skills", fake_sync_skl)

    payload = {"session_id": "x", "cwd": "/home/opc/ASEP"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    on_start.main()
    fake_sync_mem.assert_called_once()
    fake_sync_skl.assert_called_once()


def test_on_start_emits_proposal_context_when_present(monkeypatch, tmp_path, capsys):
    """When build_proposal_context returns text, SessionStart emits a
    hookSpecificOutput JSON so Claude sees a system reminder."""
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", MagicMock(return_value=True))
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_memories", MagicMock(return_value=[]))
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_skills", MagicMock(return_value=[]))
    monkeypatch.setattr(
        "tools.journal.hooks.on_start.build_proposal_context",
        lambda **kw: "📓 surface this",
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": "/home/opc/ASEP"})))
    on_start.main()
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert parsed["hookSpecificOutput"]["additionalContext"] == "📓 surface this"


def test_on_start_emits_nothing_when_no_proposals(monkeypatch, tmp_path, capsys):
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", MagicMock(return_value=True))
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_memories", MagicMock(return_value=[]))
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_skills", MagicMock(return_value=[]))
    monkeypatch.setattr(
        "tools.journal.hooks.on_start.build_proposal_context",
        lambda **kw: None,
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": "/home/opc/ASEP"})))
    on_start.main()
    assert capsys.readouterr().out == ""


def test_on_start_emits_locked_warning_when_repo_locked(monkeypatch, tmp_path, capsys):
    """When is_repo_unlocked returns False, SessionStart surfaces a
    warning even if there are no proposals."""
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", MagicMock(return_value=True))
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_memories", MagicMock(return_value=[]))
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_skills", MagicMock(return_value=[]))
    monkeypatch.setattr("tools.journal.hooks.on_start.is_repo_unlocked", lambda _repo: False)
    monkeypatch.setattr(
        "tools.journal.hooks.on_start.build_proposal_context",
        lambda **kw: None,
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": "/home/opc/ASEP"})))
    on_start.main()
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "locked" in parsed["hookSpecificOutput"]["additionalContext"].lower()


def test_on_start_combines_locked_warning_with_proposals(monkeypatch, tmp_path, capsys):
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", MagicMock(return_value=True))
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_memories", MagicMock(return_value=[]))
    monkeypatch.setattr("tools.journal.hooks.on_start.sync_all_skills", MagicMock(return_value=[]))
    monkeypatch.setattr("tools.journal.hooks.on_start.is_repo_unlocked", lambda _repo: False)
    monkeypatch.setattr(
        "tools.journal.hooks.on_start.build_proposal_context",
        lambda **kw: "📓 surface this",
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": "/home/opc/ASEP"})))
    on_start.main()
    out = capsys.readouterr().out
    parsed = json.loads(out)
    ctx = parsed["hookSpecificOutput"]["additionalContext"]
    assert "locked" in ctx.lower()
    assert "📓 surface this" in ctx


def test_pull_journal_returns_false_when_not_a_git_repo(tmp_path):
    not_a_repo = tmp_path / "fake"
    not_a_repo.mkdir()
    assert pull_module.pull_journal(not_a_repo) is False


def test_pull_journal_calls_git_pull_when_repo_exists(monkeypatch, tmp_path):
    journal = tmp_path / "claude-journal"
    (journal / ".git").mkdir(parents=True)
    captured: list[list[str]] = []

    def fake_run_git(args, cwd):
        captured.append(args)
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("tools.journal.pull._run_git", fake_run_git)
    assert pull_module.pull_journal(journal) is True
    assert captured == [["git", "pull", "--rebase", "--quiet"]]
