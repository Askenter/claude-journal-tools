from pathlib import Path
from tools.journal.surface_proposals import (
    project_key_from_cwd,
    build_proposal_context,
)


def test_project_key_from_cwd_replaces_slashes():
    assert project_key_from_cwd("/home/opc/ASEP") == "-home-opc-ASEP"


def test_no_proposals_returns_none(tmp_path: Path):
    journal = tmp_path / "journal"
    (journal / "proposals").mkdir(parents=True)
    out = build_proposal_context(journal_repo=journal, cwd="/home/opc/ASEP")
    assert out is None


def test_proposals_dir_missing_returns_none(tmp_path: Path):
    journal = tmp_path / "journal"
    journal.mkdir()
    out = build_proposal_context(journal_repo=journal, cwd="/home/opc/ASEP")
    assert out is None


def test_lists_only_current_projects_proposals(tmp_path: Path):
    journal = tmp_path / "journal"
    proposals = journal / "proposals"
    proposals.mkdir(parents=True)
    (proposals / "2026-04-28--home-opc-ASEP.md").write_text(
        "## feedback proposal — 2026-04-28T10:00:00Z\n\n"
        "Don't mock the database in tests.\n"
    )
    (proposals / "2026-04-28--home-other-project.md").write_text(
        "## feedback proposal — different project\n"
    )

    out = build_proposal_context(journal_repo=journal, cwd="/home/opc/ASEP")
    assert out is not None
    assert "2026-04-28--home-opc-ASEP.md" in out
    assert "other-project" not in out


def test_uses_first_heading_as_summary(tmp_path: Path):
    journal = tmp_path / "journal"
    proposals = journal / "proposals"
    proposals.mkdir(parents=True)
    (proposals / "2026-04-29--home-opc-ASEP.md").write_text(
        "Some preamble\n\n"
        "## CLAUDE.md edit — replace Swarm with Compose\n\n"
        "details follow\n"
    )
    out = build_proposal_context(journal_repo=journal, cwd="/home/opc/ASEP")
    assert "CLAUDE.md edit — replace Swarm with Compose" in out


def test_advertises_journal_slash_command(tmp_path: Path):
    journal = tmp_path / "journal"
    proposals = journal / "proposals"
    proposals.mkdir(parents=True)
    (proposals / "2026-04-29--home-opc-ASEP.md").write_text("## something\n")
    out = build_proposal_context(journal_repo=journal, cwd="/home/opc/ASEP")
    assert "/journal accept" in out
    assert "/journal skip" in out
    assert "/journal edit" in out


def test_labels_new_skill_proposal(tmp_path: Path):
    journal = tmp_path / "journal"
    proposals = journal / "proposals"
    proposals.mkdir(parents=True)
    (proposals / "2026-06-08--home-opc-ASEP.md").write_text(
        "## New skill: condition-based-waiting\n\n"
        "- **kind:** new-skill\n"
        "- **scope:** global\n"
    )
    out = build_proposal_context(journal_repo=journal, cwd="/home/opc/ASEP")
    assert out is not None
    assert "[new skill]" in out
    assert "New skill: condition-based-waiting" in out


def test_labels_each_entry_in_mixed_file(tmp_path: Path):
    journal = tmp_path / "journal"
    proposals = journal / "proposals"
    proposals.mkdir(parents=True)
    (proposals / "2026-06-08--home-opc-ASEP.md").write_text(
        "## New skill: foo\n\n- **kind:** new-skill\n- **scope:** global\n\n"
        "## feedback proposal — be terse\n\n```\ntype: feedback\n```\n\n"
        "## CLAUDE.md edit — update deploy\n\n- **target:** ASEP/CLAUDE.md\n"
    )
    out = build_proposal_context(journal_repo=journal, cwd="/home/opc/ASEP")
    assert "[new skill]" in out
    assert "[feedback rule]" in out
    assert "[CLAUDE.md edit]" in out
