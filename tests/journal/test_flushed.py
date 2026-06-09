from tools.journal import flushed


def test_read_empty_when_missing(tmp_path):
    assert flushed.read_flushed(tmp_path / "nope") == set()


def test_mark_and_read(tmp_path):
    p = tmp_path / "flushed"
    flushed.mark_flushed(p, "sess-a")
    flushed.mark_flushed(p, "sess-b")
    assert flushed.read_flushed(p) == {"sess-a", "sess-b"}
    assert flushed.is_flushed(p, "sess-a")
    assert not flushed.is_flushed(p, "sess-z")


def test_mark_is_idempotent(tmp_path):
    p = tmp_path / "flushed"
    flushed.mark_flushed(p, "sess-a")
    flushed.mark_flushed(p, "sess-a")
    assert p.read_text().count("sess-a") == 1


def test_empty_session_id_is_noop(tmp_path):
    p = tmp_path / "flushed"
    flushed.mark_flushed(p, "")
    assert not p.exists()
    assert not flushed.is_flushed(p, "")


def test_trims_to_keep_last(tmp_path):
    p = tmp_path / "flushed"
    for i in range(10):
        flushed.mark_flushed(p, f"sess-{i}", keep_last=3)
    kept = flushed.read_flushed(p)
    assert kept == {"sess-7", "sess-8", "sess-9"}
