import json

from tools.journal.autoupdate import enable_marketplace_autoupdate


def _known(tmp_path, *, name="claude-journal-tools", repo="askenter/claude-journal-tools"):
    p = tmp_path / "known_marketplaces.json"
    p.write_text(json.dumps({
        name: {
            "source": {"source": "github", "repo": repo},
            "installLocation": "/x",
            "lastUpdated": "t",
        }
    }))
    return p


def test_enables_and_derives_name_and_source(tmp_path):
    settings = tmp_path / "settings.json"
    changed, msg = enable_marketplace_autoupdate(
        settings_path=settings, known_marketplaces_path=_known(tmp_path),
    )
    assert changed is True
    entry = json.loads(settings.read_text())["extraKnownMarketplaces"]["claude-journal-tools"]
    assert entry["autoUpdate"] is True
    assert entry["source"] == {"source": "github", "repo": "askenter/claude-journal-tools"}


def test_idempotent(tmp_path):
    settings = tmp_path / "settings.json"
    known = _known(tmp_path)
    enable_marketplace_autoupdate(settings_path=settings, known_marketplaces_path=known)
    changed, msg = enable_marketplace_autoupdate(settings_path=settings, known_marketplaces_path=known)
    assert changed is False
    assert "already enabled" in msg


def test_preserves_existing_keys_and_other_marketplaces(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "theme": "dark",
        "extraKnownMarketplaces": {
            "other": {"source": {"source": "github", "repo": "x/other"}, "autoUpdate": False},
        },
    }))
    enable_marketplace_autoupdate(settings_path=settings, known_marketplaces_path=_known(tmp_path))
    d = json.loads(settings.read_text())
    assert d["theme"] == "dark"
    assert d["extraKnownMarketplaces"]["other"]["source"]["repo"] == "x/other"
    assert d["extraKnownMarketplaces"]["other"]["autoUpdate"] is False
    assert d["extraKnownMarketplaces"]["claude-journal-tools"]["autoUpdate"] is True


def test_uses_registered_name_not_default(tmp_path):
    settings = tmp_path / "settings.json"
    known = _known(tmp_path, name="my-cjt", repo="someone/claude-journal-tools")
    enable_marketplace_autoupdate(settings_path=settings, known_marketplaces_path=known)
    ekm = json.loads(settings.read_text())["extraKnownMarketplaces"]
    assert "my-cjt" in ekm
    assert "claude-journal-tools" not in ekm  # didn't invent a duplicate name


def test_matches_git_url_source(tmp_path):
    settings = tmp_path / "settings.json"
    known = tmp_path / "known.json"
    known.write_text(json.dumps({
        "cjt": {"source": {"source": "git", "url": "https://github.com/askenter/claude-journal-tools.git"}},
    }))
    changed, _ = enable_marketplace_autoupdate(settings_path=settings, known_marketplaces_path=known)
    assert changed is True
    assert json.loads(settings.read_text())["extraKnownMarketplaces"]["cjt"]["autoUpdate"] is True


def test_skips_when_not_a_marketplace_install(tmp_path):
    settings = tmp_path / "settings.json"
    known = tmp_path / "known.json"
    known.write_text(json.dumps({"some-other": {"source": {"source": "github", "repo": "x/y"}}}))
    changed, msg = enable_marketplace_autoupdate(settings_path=settings, known_marketplaces_path=known)
    assert changed is False
    assert "not a plugin install" in msg
    assert not settings.exists()


def test_skips_when_no_known_file(tmp_path):
    settings = tmp_path / "settings.json"
    changed, msg = enable_marketplace_autoupdate(
        settings_path=settings, known_marketplaces_path=tmp_path / "missing.json",
    )
    assert changed is False
    assert "not a plugin install" in msg


def test_invalid_settings_not_clobbered(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{not json")
    changed, msg = enable_marketplace_autoupdate(
        settings_path=settings, known_marketplaces_path=_known(tmp_path),
    )
    assert changed is False
    assert "WARNING" in msg
    assert settings.read_text() == "{not json"  # left untouched
