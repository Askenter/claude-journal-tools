from tools.journal import recall


def _mk_raw(repo, device, date_str, sid="s1"):
    d = repo / "raw" / device / date_str
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.json").write_text("{}")


def _mk_digest(repo, device, date_str, body="# digest\n"):
    d = repo / "digests" / date_str
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{device}.md").write_text(body)


def _mk_memory(repo, project, slug, body="# m\n"):
    d = repo / "memories" / project
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(body)


# --- inventory_dates ---------------------------------------------------------

def test_dates_ok_when_digest_covers_raw(tmp_path):
    repo = tmp_path / "repo"
    _mk_raw(repo, "laptop", "2026-06-08")
    _mk_digest(repo, "laptop", "2026-06-08")
    inv = recall.inventory_dates(repo, ["2026-06-08"])
    assert inv["dates"]["2026-06-08"]["status"] == "ok"
    assert inv["gaps"] == []
    assert inv["dates"]["2026-06-08"]["digests"][0].endswith("digests/2026-06-08/laptop.md")


def test_dates_gap_when_raw_but_no_digest(tmp_path):
    repo = tmp_path / "repo"
    _mk_raw(repo, "laptop", "2026-06-08")
    inv = recall.inventory_dates(repo, ["2026-06-08"])
    assert inv["dates"]["2026-06-08"]["status"] == "gap"
    assert inv["gaps"] == ["2026-06-08"]


def test_dates_partial_when_one_device_missing_digest(tmp_path):
    repo = tmp_path / "repo"
    _mk_raw(repo, "laptop", "2026-06-08")
    _mk_digest(repo, "laptop", "2026-06-08")
    _mk_raw(repo, "workstation", "2026-06-08")  # no digest for workstation
    inv = recall.inventory_dates(repo, ["2026-06-08"])
    d = inv["dates"]["2026-06-08"]
    assert d["status"] == "partial"
    assert d["missing_digest_devices"] == ["workstation"]
    assert "2026-06-08" in inv["gaps"]


def test_dates_empty_when_nothing_captured(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    inv = recall.inventory_dates(repo, ["2026-06-08"])
    assert inv["dates"]["2026-06-08"]["status"] == "empty"
    assert inv["empty"] == ["2026-06-08"]


def test_dates_multi_device_digests_listed(tmp_path):
    repo = tmp_path / "repo"
    for dev in ("laptop", "workstation"):
        _mk_raw(repo, dev, "2026-06-08")
        _mk_digest(repo, dev, "2026-06-08")
    inv = recall.inventory_dates(repo, ["2026-06-08"])
    assert inv["dates"]["2026-06-08"]["status"] == "ok"
    assert len(inv["dates"]["2026-06-08"]["digests"]) == 2


# --- inventory_memories ------------------------------------------------------

def test_memories_grouped_by_project_with_index(tmp_path):
    repo = tmp_path / "repo"
    _mk_memory(repo, "-home-you-proj", "fact-a")
    (repo / "memories" / "-home-you-proj" / "MEMORY.md").write_text("# index\n")
    out = recall.inventory_memories(repo)
    proj = out["projects"]["-home-you-proj"]
    assert proj["index"].endswith("MEMORY.md")
    assert any(f.endswith("fact-a.md") for f in proj["files"])
    assert all(not f.endswith("MEMORY.md") for f in proj["files"])


def test_memories_project_filter(tmp_path):
    repo = tmp_path / "repo"
    _mk_memory(repo, "-proj-a", "x")
    _mk_memory(repo, "-proj-b", "y")
    out = recall.inventory_memories(repo, project="-proj-a")
    assert set(out["projects"]) == {"-proj-a"}


def test_memories_empty_when_none(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert recall.inventory_memories(repo) == {"projects": {}}


def test_memories_index_none_when_absent(tmp_path):
    repo = tmp_path / "repo"
    _mk_memory(repo, "-proj", "only-fact")
    out = recall.inventory_memories(repo)
    assert out["projects"]["-proj"]["index"] is None


# --- plan --------------------------------------------------------------------

def _stub_plan_env(monkeypatch, *, unlocked=True):
    monkeypatch.setattr("tools.journal.recall.pull_journal", lambda r: True)
    monkeypatch.setattr("tools.journal.recall.is_repo_unlocked", lambda r: unlocked)


def test_plan_aborts_when_locked(monkeypatch, tmp_path):
    _stub_plan_env(monkeypatch, unlocked=False)
    res = recall.plan(tmp_path / "repo", "dates", ["2026-06-08"])
    assert res["ok"] is False
    assert res["error"] == "locked"


def test_plan_rejects_bad_date(monkeypatch, tmp_path):
    _stub_plan_env(monkeypatch)
    res = recall.plan(tmp_path / "repo", "dates", ["2026-6-8"])
    assert res["ok"] is False
    assert res["error"] == "bad-date"


def test_plan_dates_returns_inventory(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _mk_raw(repo, "laptop", "2026-06-08")
    _mk_digest(repo, "laptop", "2026-06-08")
    _stub_plan_env(monkeypatch)
    res = recall.plan(repo, "dates", ["2026-06-08"])
    assert res["ok"] is True
    assert res["mode"] == "dates"
    assert res["dates"]["2026-06-08"]["status"] == "ok"


def test_plan_memories_returns_projects(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _mk_memory(repo, "-proj", "fact")
    _stub_plan_env(monkeypatch)
    res = recall.plan(repo, "memories", [])
    assert res["ok"] is True
    assert res["mode"] == "memories"
    assert "-proj" in res["projects"]


def test_plan_dates_requires_a_date(monkeypatch, tmp_path):
    _stub_plan_env(monkeypatch)
    res = recall.plan(tmp_path / "repo", "dates", [])
    assert res["ok"] is False
    assert res["error"] == "usage"


# --- main dispatch -----------------------------------------------------------

def test_main_unknown_subcommand():
    assert recall.main(["bogus"]) == 2


def test_main_no_subcommand():
    assert recall.main([]) == 2
