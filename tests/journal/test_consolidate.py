import datetime as dt
import subprocess
from unittest.mock import MagicMock

from tools.journal import consolidate

TODAY = dt.date(2026, 6, 9)


def _mk_raw(repo, device, date_str, sid="s1"):
    d = repo / "raw" / device / date_str
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.json").write_text("{}")


def _mk_digest(repo, device, date_str):
    d = repo / "digests" / date_str
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{device}.md").write_text("# digest\n")


# --- compute_pending_dates ---------------------------------------------------

def test_today_and_yesterday_always_pending_even_with_digest(tmp_path):
    repo = tmp_path / "repo"
    for ds in ("2026-06-09", "2026-06-08"):
        _mk_raw(repo, "laptop", ds)
        _mk_digest(repo, "laptop", ds)  # fully digested, but still refreshed
    pending = consolidate.compute_pending_dates(repo, TODAY)
    assert pending == ["2026-06-08", "2026-06-09"]


def test_missing_digest_is_backfilled(tmp_path):
    repo = tmp_path / "repo"
    _mk_raw(repo, "laptop", "2026-06-05")  # 4 days ago, no digest
    pending = consolidate.compute_pending_dates(repo, TODAY)
    assert pending == ["2026-06-05"]


def test_fully_consolidated_older_date_excluded(tmp_path):
    repo = tmp_path / "repo"
    _mk_raw(repo, "laptop", "2026-06-04")
    _mk_digest(repo, "laptop", "2026-06-04")
    assert consolidate.compute_pending_dates(repo, TODAY) == []


def test_lookback_bound_excludes_old_dates(tmp_path):
    repo = tmp_path / "repo"
    _mk_raw(repo, "laptop", "2026-05-20")  # >14 days before, no digest
    assert consolidate.compute_pending_dates(repo, TODAY) == []


def test_per_device_missing_digest_backfills_whole_date(tmp_path):
    repo = tmp_path / "repo"
    _mk_raw(repo, "laptop", "2026-06-03")
    _mk_digest(repo, "laptop", "2026-06-03")
    _mk_raw(repo, "workstation", "2026-06-03")  # this device has no digest
    assert "2026-06-03" in consolidate.compute_pending_dates(repo, TODAY)


def test_empty_repo_has_nothing_pending(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert consolidate.compute_pending_dates(repo, TODAY) == []


def test_rolling_date_refreshes_even_when_all_devices_digested(tmp_path):
    """The today/yesterday short-circuit must fire regardless of per-device
    digest coverage, so a reorder that put the digest check first can't stop
    today from refreshing."""
    repo = tmp_path / "repo"
    for dev in ("laptop", "workstation"):
        _mk_raw(repo, dev, "2026-06-09")
        _mk_digest(repo, dev, "2026-06-09")
    assert "2026-06-09" in consolidate.compute_pending_dates(repo, TODAY)


def test_non_canonical_date_dirs_skipped(tmp_path):
    repo = tmp_path / "repo"
    for bad in ("2026-06-7", "2026-6-07", "not-a-date", "2026-13-01"):
        d = repo / "raw" / "laptop" / bad
        d.mkdir(parents=True)
        (d / "s1.json").write_text("{}")
    assert consolidate.compute_pending_dates(repo, TODAY) == []


def test_stray_entries_ignored(tmp_path):
    repo = tmp_path / "repo"
    (repo / "raw").mkdir(parents=True)
    (repo / "raw" / ".DS_Store").write_text("junk")  # device-level non-dir
    (repo / "raw" / "laptop").mkdir()
    (repo / "raw" / "laptop" / "stray.json").write_text("{}")  # date-parent non-dir
    empty = repo / "raw" / "laptop" / "2026-06-09"
    empty.mkdir()  # date dir with no *.json
    (empty / ".gitkeep").write_text("")
    assert consolidate.compute_pending_dates(repo, TODAY) == []


# --- live_transcript_path ----------------------------------------------------

def test_live_transcript_path_derives_from_cwd(monkeypatch, tmp_path):
    home = tmp_path / "home"
    proj = home / ".claude" / "projects" / "-Users-me-proj"
    proj.mkdir(parents=True)
    t = proj / "sid.jsonl"
    t.write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    assert consolidate.live_transcript_path("sid", cwd="/Users/me/proj") == t


def test_live_transcript_path_glob_fallback(monkeypatch, tmp_path):
    home = tmp_path / "home"
    proj = home / ".claude" / "projects" / "-weird.proj"
    proj.mkdir(parents=True)
    t = proj / "sess-x.jsonl"
    t.write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    # The cwd-derived slug won't match, so the unique-id glob must find it.
    assert consolidate.live_transcript_path("sess-x", cwd="/whatever/weird.proj") == t


# --- flush_current_session ---------------------------------------------------

def test_flush_captures_and_marks(monkeypatch, tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}")
    flushed_file = tmp_path / "flushed"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-live")
    monkeypatch.setattr("tools.journal.consolidate.live_transcript_path", lambda sid, cwd=None: transcript)
    fake_capture = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.consolidate.capture_session", fake_capture)
    monkeypatch.setattr("tools.journal.consolidate.read_device_name", lambda: "laptop")
    monkeypatch.setattr("tools.journal.consolidate.flushed_sessions_path", lambda: flushed_file)

    sid = consolidate.flush_current_session()

    assert sid == "sess-live"
    fake_capture.assert_called_once()
    assert "sess-live" in flushed_file.read_text()


def test_flush_noop_without_session_env(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert consolidate.flush_current_session() is None


# --- plan --------------------------------------------------------------------

def _stub_plan_env(monkeypatch):
    monkeypatch.setattr("tools.journal.consolidate.flush_current_session", lambda: None)
    monkeypatch.setattr("tools.journal.consolidate.pull_journal", lambda r: True)


def test_plan_force_date(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / "consolidator").mkdir(parents=True)
    _stub_plan_env(monkeypatch)
    monkeypatch.setattr("tools.journal.consolidate.is_repo_unlocked", lambda r: True)
    res = consolidate.plan(repo, force_date="2026-06-01")
    assert res["ok"] is True
    assert res["dates"] == ["2026-06-01"]
    assert res["routine"].endswith("consolidator/ROUTINE.md")


def test_plan_aborts_when_locked(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _stub_plan_env(monkeypatch)
    monkeypatch.setattr("tools.journal.consolidate.is_repo_unlocked", lambda r: False)
    res = consolidate.plan(repo)
    assert res["ok"] is False
    assert res["error"] == "locked"


def test_plan_rejects_bad_force_date(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _stub_plan_env(monkeypatch)
    monkeypatch.setattr("tools.journal.consolidate.is_repo_unlocked", lambda r: True)
    res = consolidate.plan(repo, force_date="not-a-date")
    assert res["ok"] is False
    assert res["error"] == "bad-date"


def test_plan_keys_off_utc_clock(monkeypatch, tmp_path):
    """plan() must derive the window from _today_utc(), not the local date."""
    repo = tmp_path / "repo"
    (repo / "consolidator").mkdir(parents=True)
    _mk_raw(repo, "laptop", "2026-03-15")
    _stub_plan_env(monkeypatch)
    monkeypatch.setattr("tools.journal.consolidate.is_repo_unlocked", lambda r: True)
    monkeypatch.setattr("tools.journal.consolidate._today_utc", lambda: dt.date(2026, 3, 15))
    res = consolidate.plan(repo)
    assert res["ok"] is True
    assert "2026-03-15" in res["dates"]


# --- finalize ----------------------------------------------------------------

def _init_git(repo):
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def test_finalize_nothing_when_no_derived_dirs(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    spy = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.consolidate._commit_and_push", spy)
    res = consolidate.finalize(repo)
    assert res["changed"] is False
    spy.assert_not_called()


def test_finalize_skips_when_index_clean(tmp_path):
    repo = tmp_path / "repo"
    _init_git(repo)
    _mk_digest(repo, "laptop", "2026-06-09")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add digest"], cwd=repo, check=True)
    res = consolidate.finalize(repo)
    assert res["changed"] is False


def test_finalize_commits_and_pushes_when_dirty(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git(repo)
    _mk_digest(repo, "laptop", "2026-06-09")  # new, unstaged
    spy = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.consolidate._commit_and_push", spy)
    res = consolidate.finalize(repo)
    assert res["changed"] is True
    assert res["pushed"] is True
    spy.assert_called_once()


def test_commit_and_push_retries_with_backoff(monkeypatch, tmp_path):
    """A rejected push rebases and retries with 1/4/16 backoff; no trailing
    sleep after a successful push."""
    class _R:
        def __init__(self, rc):
            self.returncode = rc

    push_results = iter([_R(1), _R(1), _R(0)])  # push fails twice, then succeeds

    def fake_git(args, cwd):
        if args[:2] == ["git", "push"]:
            return next(push_results)
        return _R(0)

    sleeps = []
    monkeypatch.setattr("tools.journal.consolidate._run_git", fake_git)
    monkeypatch.setattr("tools.journal.consolidate.time.sleep", lambda s: sleeps.append(s))

    ok = consolidate._commit_and_push(tmp_path / "repo", ["digests"], "msg")

    assert ok is True
    assert sleeps == [1, 4]  # slept before retry 1 and retry 2, not after success


# --- main dispatch -----------------------------------------------------------

def test_main_unknown_subcommand(capsys):
    assert consolidate.main(["bogus"]) == 2


def test_main_no_subcommand(capsys):
    assert consolidate.main([]) == 2
