from pathlib import Path
from tools.journal.state import (
    read_project_claudemd,
    write_state_claudemd,
)


def test_read_returns_none_when_missing(tmp_path: Path):
    assert read_project_claudemd(tmp_path) is None


def test_read_returns_text_when_present(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text("# Project guide\n\nfoo\n")
    out = read_project_claudemd(tmp_path)
    assert out is not None
    assert "Project guide" in out


def test_read_redacts_token_patterns(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text(
        "# guide\n\nDEBUG: sk-ant-oat01-AAABBBCCCDDDEEEFFFGGG never leak\n"
    )
    out = read_project_claudemd(tmp_path)
    assert "sk-ant-oat01" not in out
    assert "[REDACTED]" in out


def test_write_lands_at_state_per_project_path(tmp_path: Path):
    journal = tmp_path / "journal"
    target = write_state_claudemd(
        journal_repo=journal,
        project_key="-home-opc-ASEP",
        content="# CLAUDE.md content\n",
    )
    assert target == journal / "state" / "-home-opc-ASEP" / "CLAUDE.md"
    assert target.read_text() == "# CLAUDE.md content\n"


def test_write_sanitizes_traversal_in_project_key(tmp_path: Path):
    journal = tmp_path / "journal"
    target = write_state_claudemd(
        journal_repo=journal,
        project_key="../../../etc/passwd",
        content="# evil\n",
    )
    # Must be inside journal/state/ and not have escaped.
    assert journal in target.parents
    assert "passwd" in target.parts[-2]
    assert ".." not in target.parts


def test_write_appends_trailing_newline_when_missing(tmp_path: Path):
    journal = tmp_path / "journal"
    target = write_state_claudemd(
        journal_repo=journal,
        project_key="p",
        content="no newline",
    )
    assert target.read_text() == "no newline\n"
