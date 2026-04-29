import json
from tools.journal.transcript import extract_transcript_text


def _write_jsonl(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def test_extracts_user_and_assistant_text(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_jsonl(transcript, [
        {"type": "user", "message": {"content": "Help me build X."}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Sure, let's start by..."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        ]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "Great."}]}},
    ])
    out = extract_transcript_text(transcript)
    assert "## User" in out
    assert "## Assistant" in out
    assert "Help me build X." in out
    assert "Sure, let's start by" in out
    assert "Great." in out
    # Tool use entries are dropped — they don't help memory extraction.
    assert "tool_use" not in out
    assert "ls" not in out


def test_returns_empty_for_missing_file(tmp_path):
    assert extract_transcript_text(tmp_path / "does-not-exist.jsonl") == ""


def test_returns_empty_for_empty_jsonl(tmp_path):
    transcript = tmp_path / "empty.jsonl"
    transcript.write_text("")
    assert extract_transcript_text(transcript) == ""


def test_skips_non_user_non_assistant_entries(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_jsonl(transcript, [
        {"type": "system", "message": {"content": "metadata only"}},
        {"type": "user", "message": {"content": "real prompt"}},
    ])
    out = extract_transcript_text(transcript)
    assert "real prompt" in out
    assert "metadata only" not in out


def test_tail_truncates_when_over_budget(tmp_path):
    transcript = tmp_path / "t.jsonl"
    early = "x" * 5000
    late = "y" * 5000
    _write_jsonl(transcript, [
        {"type": "user", "message": {"content": early}},
        {"type": "user", "message": {"content": late}},
    ])
    out = extract_transcript_text(transcript, budget_bytes=6000)
    assert late in out
    assert early not in out
    assert "truncated" in out


def test_redacts_token_patterns(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_jsonl(transcript, [
        {"type": "user", "message": {"content": "my key sk-ant-oat01-AAABBBCCCDDDEEEFFFGGG please don't log this"}},
    ])
    out = extract_transcript_text(transcript)
    assert "sk-ant-oat01" not in out
    assert "[REDACTED]" in out


def test_redacts_git_crypt_keyfile_base64(tmp_path):
    # Every git-crypt symmetric keyfile, base64-encoded, starts with
    # "AEdJVENSWVBU" (base64 of "\x00GITCRYPT"). Transcripts that quote
    # such a key must scrub it before pushing.
    fake_key_b64 = (
        "AEdJVENSWVBUS0VZAAAAAgAAAAAAAAABAAAABAAAAAAAAAADAAAAIHQa168sk20F"
        "xWezedRyyLrvpfOF+x4KzjXi6RdDZCCGAAAABQAAAECFDFhZAY1kMEbSZlIwOQ7r"
        "nGhtRZhZYW9DGbaz3M7NWt+W+qo8wBQxuh1lKWjGZ6AKHri4j3yABxIwd7CWlo78"
        "AAAAAA=="
    )
    transcript = tmp_path / "t.jsonl"
    _write_jsonl(transcript, [
        {"type": "user", "message": {"content": f"key is {fake_key_b64} keep secret"}},
    ])
    out = extract_transcript_text(transcript)
    assert fake_key_b64 not in out
    assert "AEdJVENSWVBU" not in out
    assert "[REDACTED]" in out


def test_skips_malformed_jsonl_lines(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        "not json\n"
        + json.dumps({"type": "user", "message": {"content": "good"}}) + "\n"
        + "}{\n"
    )
    out = extract_transcript_text(transcript)
    assert "good" in out


def test_handles_assistant_text_only_entries(tmp_path):
    """An assistant entry whose content is a list of just tool_use/tool_result
    items (no text) should be silently dropped, not produce an empty header."""
    transcript = tmp_path / "t.jsonl"
    _write_jsonl(transcript, [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        ]}},
        {"type": "user", "message": {"content": "hi"}},
    ])
    out = extract_transcript_text(transcript)
    assert out.count("## Assistant") == 0
    assert out.count("## User") == 1
