from datetime import datetime, timezone
from pathlib import Path
from tools.journal.extract import extract_structural

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_structural_from_transcript():
    out = extract_structural(
        session_id="sess-1",
        device="laptop",
        project_dir="/home/you/myproject",
        transcript_path=FIXTURES / "transcript_simple.jsonl",
    )
    assert out["session_id"] == "sess-1"
    assert out["device"] == "laptop"
    assert out["project"] == "-home-you-myproject"
    assert out["files_touched"] == ["src/api.py", "frontend/components/Header.tsx"]
    assert out["skills_invoked"] == ["superpowers:brainstorming"]
    assert out["first_prompt"].startswith("Add a new endpoint")
    assert out["started_at"] == datetime(2026, 4, 28, 9, 0, 0, tzinfo=timezone.utc)
    assert out["ended_at"]   == datetime(2026, 4, 28, 9, 30, 0, tzinfo=timezone.utc)


def test_extract_handles_empty_transcript(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    out = extract_structural(
        session_id="sess-2",
        device="laptop",
        project_dir="/home/you/myproject",
        transcript_path=empty,
    )
    assert out["files_touched"] == []
    assert out["skills_invoked"] == []
    assert out["first_prompt"] == ""
    assert out["started_at"] is None
    assert out["ended_at"] is None


def test_extract_handles_missing_transcript():
    out = extract_structural(
        session_id="sess-3",
        device="laptop",
        project_dir="/home/you/myproject",
        transcript_path=Path("/nonexistent/transcript.jsonl"),
    )
    assert out["files_touched"] == []
    assert out["first_prompt"] == ""
    assert out["started_at"] is None
    assert out["ended_at"] is None


def test_first_prompt_is_redacted(tmp_path):
    """A secret pasted as the first user message must not survive into the
    breadcrumb's first_prompt field (raw/ JSON is encrypted, but redaction is
    the documented layer 2 and must cover every pushed text field)."""
    # Assembled at runtime so the fixture itself never looks like a real
    # credential to push protection.
    token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "k1L2m3N4o5"
    t = tmp_path / "t.jsonl"
    t.write_text(
        '{"type":"user","timestamp":"2026-04-28T09:00:00Z","message":{"content":'
        + '"here is my token ' + token + ' please use it"}}\n'
    )
    out = extract_structural(
        session_id="sess-r",
        device="laptop",
        project_dir="/home/you/myproject",
        transcript_path=t,
    )
    assert token not in out["first_prompt"]
    assert "[REDACTED]" in out["first_prompt"]


def test_first_prompt_redacts_before_truncating(tmp_path):
    """Redaction must run on the full message BEFORE the 200-char truncation.
    A key straddling the truncation boundary would otherwise be cut to a
    fragment too short to match any pattern, leaking a partial secret."""
    token = "ghp_" + "z9Y8x7W6v5U4t3S2r1Q0" + "p9O8n7M6l5"
    # 190 chars of prose, then the key — naive truncate-then-redact keeps
    # the first ~10 chars of the key.
    prose = "word " * 38
    t = tmp_path / "t.jsonl"
    t.write_text(
        '{"type":"user","timestamp":"2026-04-28T09:00:00Z","message":{"content":'
        + '"' + prose + token + '"}}\n'
    )
    out = extract_structural(
        session_id="sess-r2",
        device="laptop",
        project_dir="/home/you/myproject",
        transcript_path=t,
    )
    assert "ghp_" not in out["first_prompt"]


def test_extract_tolerates_malformed_timestamps(tmp_path):
    """The Stop hook never blocks on bad data — a non-string or non-ISO
    timestamp on one line must not abort extraction of the whole session."""
    bad = tmp_path / "bad_ts.jsonl"
    bad.write_text(
        '{"type":"user","timestamp":12345,"message":{"content":"first"}}\n'
        '{"type":"user","timestamp":"not-a-date","message":{"content":"second"}}\n'
        '{"type":"assistant","timestamp":"2026-04-28T09:00:00Z","message":{"content":[{"type":"tool_use","name":"Edit","input":{"file_path":"src/api.py"}}]}}\n'
        '{"type":"assistant","timestamp":"2026-04-28T09:30:00Z","message":{"content":"done"}}\n'
    )
    out = extract_structural(
        session_id="sess-bad",
        device="laptop",
        project_dir="/home/you/myproject",
        transcript_path=bad,
    )
    # The two malformed-timestamp lines are still processed for content
    # (first_prompt picks the first user message), but their timestamps are
    # silently dropped — only the well-formed timestamps set started/ended.
    assert out["first_prompt"] == "first"
    assert out["files_touched"] == ["src/api.py"]
    assert out["started_at"] == datetime(2026, 4, 28, 9, 0, 0, tzinfo=timezone.utc)
    assert out["ended_at"] == datetime(2026, 4, 28, 9, 30, 0, tzinfo=timezone.utc)
