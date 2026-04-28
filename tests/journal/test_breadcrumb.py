from datetime import datetime, timezone
from tools.journal.breadcrumb import Breadcrumb


def test_breadcrumb_serializes_structural_fields():
    bc = Breadcrumb(
        session_id="abc-123",
        device="laptop",
        project="-home-opc-ASEP",
        started_at=datetime(2026, 4, 28, 9, 14, 32, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 28, 10, 2, 18, tzinfo=timezone.utc),
        files_touched=["src/api.py"],
        skills_invoked=["superpowers:brainstorming"],
        first_prompt="Help me design a memory consolidation pipeline...",
    )
    out = bc.to_dict()
    assert out == {
        "session_id": "abc-123",
        "device": "laptop",
        "project": "-home-opc-ASEP",
        "started_at": "2026-04-28T09:14:32+00:00",
        "ended_at":   "2026-04-28T10:02:18+00:00",
        "files_touched": ["src/api.py"],
        "skills_invoked": ["superpowers:brainstorming"],
        "first_prompt": "Help me design a memory consolidation pipeline...",
    }


def test_first_prompt_truncated_to_200_chars():
    long = "x" * 500
    bc = Breadcrumb(
        session_id="s", device="d", project="p",
        started_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        files_touched=[], skills_invoked=[], first_prompt=long,
    )
    assert len(bc.first_prompt) == 200
    assert len(bc.to_dict()["first_prompt"]) == 200


def test_to_dict_returns_independent_list_copies():
    files = ["src/api.py"]
    skills = ["superpowers:brainstorming"]
    bc = Breadcrumb(
        session_id="s", device="d", project="p",
        started_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        files_touched=files, skills_invoked=skills, first_prompt="",
    )
    out = bc.to_dict()
    out["files_touched"].append("intruder.py")
    out["skills_invoked"].append("intruder")
    assert bc.files_touched == ["src/api.py"]
    assert bc.skills_invoked == ["superpowers:brainstorming"]
