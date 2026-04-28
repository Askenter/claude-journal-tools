from datetime import datetime, timezone
from pathlib import Path
from tools.journal.extract import extract_structural

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_structural_from_transcript():
    out = extract_structural(
        session_id="sess-1",
        device="laptop",
        project_dir="/home/opc/ASEP",
        transcript_path=FIXTURES / "transcript_simple.jsonl",
    )
    assert out["session_id"] == "sess-1"
    assert out["device"] == "laptop"
    assert out["project"] == "-home-opc-ASEP"
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
        project_dir="/home/opc/ASEP",
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
        project_dir="/home/opc/ASEP",
        transcript_path=Path("/nonexistent/transcript.jsonl"),
    )
    assert out["files_touched"] == []
    assert out["first_prompt"] == ""
    assert out["started_at"] is None
    assert out["ended_at"] is None


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
        project_dir="/home/opc/ASEP",
        transcript_path=bad,
    )
    # The two malformed-timestamp lines are still processed for content
    # (first_prompt picks the first user message), but their timestamps are
    # silently dropped — only the well-formed timestamps set started/ended.
    assert out["first_prompt"] == "first"
    assert out["files_touched"] == ["src/api.py"]
    assert out["started_at"] == datetime(2026, 4, 28, 9, 0, 0, tzinfo=timezone.utc)
    assert out["ended_at"] == datetime(2026, 4, 28, 9, 30, 0, tzinfo=timezone.utc)
