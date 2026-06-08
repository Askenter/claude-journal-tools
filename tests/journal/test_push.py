import json
from pathlib import Path
from unittest.mock import MagicMock
from tools.journal.push import (
    push_breadcrumb,
    _drain_buffer,
    _safe_path_segment,
    _write_breadcrumb_file,
)


def _make_paths(tmp_path: Path) -> tuple[Path, Path]:
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    (journal / "raw").mkdir()
    buffer = tmp_path / "journal-buffer.jsonl"
    return journal, buffer


def _git_ok(*args, **kwargs):
    result = MagicMock()
    result.returncode = 0
    result.stdout = ""
    result.stderr = ""
    return result


def _git_fail(*args, **kwargs):
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    result.stderr = "git failed"
    return result


def test_push_writes_file_and_succeeds(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    breadcrumb = {
        "session_id": "abc-123",
        "device": "laptop",
        "project": "-home-you-myproject",
        "started_at": "2026-04-28T09:00:00+00:00",
        "ended_at": "2026-04-28T10:00:00+00:00",
    }
    ok = push_breadcrumb(
        breadcrumb=breadcrumb,
        journal_repo=journal,
        buffer_path=buffer,
        date_str="2026-04-28",
    )
    assert ok is True
    assert not buffer.exists() or buffer.read_text() == ""
    target = journal / "raw" / "laptop" / "2026-04-28" / "abc-123.json"
    assert target.exists()
    assert json.loads(target.read_text())["session_id"] == "abc-123"


def test_push_keeps_in_buffer_on_git_failure(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_fail)

    breadcrumb = {"session_id": "abc-123", "device": "laptop"}
    ok = push_breadcrumb(
        breadcrumb=breadcrumb,
        journal_repo=journal,
        buffer_path=buffer,
        date_str="2026-04-28",
    )
    assert ok is False
    assert buffer.exists()
    lines = [json.loads(l) for l in buffer.read_text().splitlines() if l.strip()]
    assert any(l.get("breadcrumb", {}).get("session_id") == "abc-123" for l in lines)


def test_drain_buffer_replays_pending(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    pending = [
        {"session_id": "old-1", "device": "laptop"},
        {"session_id": "old-2", "device": "laptop"},
    ]
    buffer.write_text("\n".join(json.dumps(p) for p in pending) + "\n")

    drained = _drain_buffer(buffer=buffer, journal_repo=journal, date_str="2026-04-28")
    assert drained == 2
    assert (journal / "raw" / "laptop" / "2026-04-28" / "old-1.json").exists()
    assert (journal / "raw" / "laptop" / "2026-04-28" / "old-2.json").exists()
    assert buffer.read_text() == ""


def test_push_exercises_commit_and_push_when_status_is_dirty(monkeypatch, tmp_path):
    """Cover the commit+push path: simulate `git diff --cached --quiet`
    reporting staged changes so _git_push runs commit + push."""
    journal, buffer = _make_paths(tmp_path)
    calls: list[list[str]] = []

    def fake_run_git(args, cwd):
        calls.append(args)
        result = MagicMock()
        # `git diff --cached --quiet` exits 1 when the index is dirty.
        result.returncode = 1 if args[:2] == ["git", "diff"] else 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr("tools.journal.push._run_git", fake_run_git)

    ok = push_breadcrumb(
        breadcrumb={"session_id": "abc-123", "device": "laptop"},
        journal_repo=journal,
        buffer_path=buffer,
        date_str="2026-04-28",
    )
    assert ok is True
    invoked = [c[:2] for c in calls]
    assert ["git", "pull"] in invoked
    assert ["git", "add"] in invoked
    assert ["git", "diff"] in invoked
    assert ["git", "commit"] in invoked
    assert ["git", "push"] in invoked
    # The pull-rebase must use --autostash so an unrelated dirty tree
    # (e.g. git-crypt smudge artefacts on .gitkeep blobs under encrypted
    # paths) doesn't wedge the push the way it did on this Mac after
    # the 2026-04-29 git-crypt unlock.
    pull_calls = [c for c in calls if c[:2] == ["git", "pull"]]
    assert pull_calls, "expected at least one git pull invocation"
    assert all("--autostash" in c for c in pull_calls)


def test_push_skips_commit_when_nothing_is_staged(monkeypatch, tmp_path):
    """Working tree may carry unstaged dirt (e.g. git-crypt smudge artefacts
    on .gitkeep blobs) that `git add -A raw/ state/` does not stage. In that
    case _git_push must skip `git commit` (which would exit 1 with "nothing
    to commit") and proceed straight to pull-rebase + push so any local-only
    commits from earlier still reach origin."""
    journal, buffer = _make_paths(tmp_path)
    calls: list[list[str]] = []

    def fake_run_git(args, cwd):
        calls.append(args)
        result = MagicMock()
        result.stdout = ""
        result.stderr = ""
        # `git diff --cached --quiet` returns 0 when the index is clean.
        if args[:2] == ["git", "diff"]:
            result.returncode = 0
        elif args[:2] == ["git", "commit"]:
            # Should never be reached in this scenario; if it is, simulate
            # the real "nothing to commit" failure so the test catches it.
            result.returncode = 1
            result.stderr = "nothing to commit, working tree clean\n"
        else:
            result.returncode = 0
        return result

    monkeypatch.setattr("tools.journal.push._run_git", fake_run_git)

    ok = push_breadcrumb(
        breadcrumb={"session_id": "no-stage", "device": "laptop"},
        journal_repo=journal,
        buffer_path=buffer,
        date_str="2026-04-28",
    )
    assert ok is True
    invoked = [c[:2] for c in calls]
    assert ["git", "commit"] not in invoked
    assert ["git", "pull"] in invoked
    assert ["git", "push"] in invoked


def test_drain_buffer_keeps_backlog_when_push_fails(monkeypatch, tmp_path):
    """If the post-drain push fails, the buffer must NOT be cleared."""
    journal, buffer = _make_paths(tmp_path)

    def fake_run_git(args, cwd):
        result = MagicMock()
        result.stdout = ""
        result.stderr = ""
        if args[:2] == ["git", "push"]:
            result.returncode = 1
        elif args[:2] == ["git", "diff"]:
            # Index has staged changes so the commit path runs.
            result.returncode = 1
        else:
            result.returncode = 0
        return result

    monkeypatch.setattr("tools.journal.push._run_git", fake_run_git)

    pending = [{"session_id": "stuck-1", "device": "laptop"}]
    buffer.write_text(json.dumps(pending[0]) + "\n")

    drained = _drain_buffer(buffer=buffer, journal_repo=journal, date_str="2026-04-28")
    assert drained == 0
    assert buffer.exists()
    assert buffer.read_text().strip() != ""


def test_drain_uses_breadcrumbs_own_started_at_for_date_bucket(monkeypatch, tmp_path):
    """A breadcrumb buffered on Monday and drained on Friday must land in
    Monday's directory, not Friday's. The breadcrumb's own started_at
    drives the directory bucket."""
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    monday_bc = {
        "session_id": "mon-sess",
        "device": "laptop",
        "started_at": "2026-04-27T15:00:00+00:00",
    }
    buffer.write_text(json.dumps(monday_bc) + "\n")

    drained = _drain_buffer(buffer=buffer, journal_repo=journal, date_str="2026-05-01")
    assert drained == 1
    assert (journal / "raw" / "laptop" / "2026-04-27" / "mon-sess.json").exists()
    assert not (journal / "raw" / "laptop" / "2026-05-01" / "mon-sess.json").exists()


def test_drain_falls_back_to_date_str_when_started_at_missing(monkeypatch, tmp_path):
    """If a buffered breadcrumb lacks started_at, use the caller's date_str."""
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    bc = {"session_id": "no-ts", "device": "laptop"}  # no started_at
    buffer.write_text(json.dumps(bc) + "\n")

    drained = _drain_buffer(buffer=buffer, journal_repo=journal, date_str="2026-05-01")
    assert drained == 1
    assert (journal / "raw" / "laptop" / "2026-05-01" / "no-ts.json").exists()


def test_safe_path_segment_blocks_traversal():
    """device and session_id are sanitized against path traversal so a
    malformed value cannot escape the journal repo tree."""
    out = _safe_path_segment("../../../etc/passwd")
    assert "/" not in out
    assert ".." not in out
    assert _safe_path_segment("normal-id") == "normal-id"
    assert _safe_path_segment("with\\backslash") == "with_backslash"


def test_push_writes_transcript_file_alongside_breadcrumb(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    breadcrumb = {
        "session_id": "abc-123",
        "device": "laptop",
        "started_at": "2026-04-28T09:00:00+00:00",
    }
    push_breadcrumb(
        breadcrumb=breadcrumb,
        journal_repo=journal,
        buffer_path=buffer,
        date_str="2026-04-28",
        transcript_text="## User\n\nhello\n",
    )
    bc_file = journal / "raw" / "laptop" / "2026-04-28" / "abc-123.json"
    tx_file = journal / "raw" / "laptop" / "2026-04-28" / "abc-123.transcript.md"
    assert bc_file.exists()
    assert tx_file.exists()
    assert "hello" in tx_file.read_text()


def test_push_skips_transcript_file_when_empty(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    push_breadcrumb(
        breadcrumb={"session_id": "no-tx", "device": "laptop"},
        journal_repo=journal,
        buffer_path=buffer,
        date_str="2026-04-28",
        transcript_text="",
    )
    tx_file = journal / "raw" / "laptop" / "2026-04-28" / "no-tx.transcript.md"
    assert not tx_file.exists()


def test_drain_replays_transcript_alongside_breadcrumb(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    payload = {
        "breadcrumb": {"session_id": "buf-1", "device": "laptop", "started_at": "2026-04-28T09:00:00+00:00"},
        "transcript": "## User\n\nbuffered prose\n",
    }
    buffer.write_text(json.dumps(payload) + "\n")

    drained = _drain_buffer(buffer=buffer, journal_repo=journal, date_str="2026-04-28")
    assert drained == 1
    tx = journal / "raw" / "laptop" / "2026-04-28" / "buf-1.transcript.md"
    assert tx.exists()
    assert "buffered prose" in tx.read_text()


def test_drain_handles_legacy_bare_breadcrumb_lines(monkeypatch, tmp_path):
    """Buffer entries from before the v2 wrapper (bare breadcrumb dicts) must
    still drain cleanly — no transcript file, just the breadcrumb."""
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    legacy = {"session_id": "legacy-1", "device": "laptop", "started_at": "2026-04-28T09:00:00+00:00"}
    buffer.write_text(json.dumps(legacy) + "\n")

    drained = _drain_buffer(buffer=buffer, journal_repo=journal, date_str="2026-04-28")
    assert drained == 1
    bc = journal / "raw" / "laptop" / "2026-04-28" / "legacy-1.json"
    tx = journal / "raw" / "laptop" / "2026-04-28" / "legacy-1.transcript.md"
    assert bc.exists()
    assert not tx.exists()


def test_write_breadcrumb_file_contains_evil_input(tmp_path):
    """A breadcrumb with traversal-style device/sid stays inside the journal
    repo tree."""
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    bad = {
        "session_id": "../../escaped",
        "device": "../../../host",
    }
    written = _write_breadcrumb_file(breadcrumb=bad, journal_repo=journal, date_str="2026-04-28")
    # Must remain within the journal repo
    assert journal in written.parents
    # Must NOT have escaped
    assert "escaped.json" not in [p.name for p in tmp_path.iterdir() if p.is_file()]
