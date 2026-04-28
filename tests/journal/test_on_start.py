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
