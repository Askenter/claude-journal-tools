# Cognitive Consolidation Pipeline — Phase 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 foundation of the cognitive consolidation pipeline — bootstrap the `claude-journal` private GitHub repo, install per-device Stop and SessionStart hooks (Python), and produce LLM-augmented breadcrumbs that flow from each device into the central repo on every session exit.

**Architecture:** Two Python hook entrypoints, registered in `~/.claude/settings.json`, that wrap pure-function modules in `tools/journal/`. The Stop hook extracts a structural breadcrumb from the session transcript, calls Haiku-4.5 to add four interpreted fields, and pushes it to the journal repo. The SessionStart hook pulls the journal repo at the start of each session (sync-and-apply logic is reserved for Phase 2). All journal logic is pure-Python in this repo (canonical source); the device installs symlinks pointing at it so updates propagate by `git pull`.

**Tech Stack:** Python 3.11+, Anthropic Python SDK (`anthropic` ≥0.40), `gh` CLI, git, pytest, pytest-mock. No new runtime services.

**Spec:** see [docs/superpowers/specs/cognitive-consolidation-design.md](../specs/cognitive-consolidation-design.md).

---

## Phase scope

Phase 1 covers **everything needed to push breadcrumbs**. No consolidator routine yet, no proposal queue, no `/journal` slash commands.

**In scope (this plan):**
- `claude-journal` repo bootstrap with the directory layout from the spec
- Breadcrumb data model + serialization
- Transcript extraction (structural fields)
- Haiku augmentation (interpreted fields, with graceful failure)
- Git push integration (with offline backlog)
- Stop hook entrypoint
- SessionStart hook entrypoint (pull-only, no apply yet)
- `init-journal-device` script for first-time per-device setup
- End-to-end smoke test on this dev box

**Out of scope (later plans):**
- Phase 2: central routine, tier-1a memory consolidation, cross-device merge, `/consolidate-now` API trigger
- Phase 3: proposal queue (tier-1b feedback, tier-3 CLAUDE.md), `/journal accept|skip|edit`
- Phase 4: tier-2 skill distillation, CHANGELOG management

Phase 1 produces working, testable software: every Claude session on every initialized device pushes one breadcrumb to `claude-journal/raw/<device>/<date>/<sid>.json`. You can verify by inspecting the repo on GitHub.

---

## File structure

```
myproject/
├── tools/journal/                          # NEW — canonical source for journal logic
│   ├── __init__.py
│   ├── breadcrumb.py                       # Breadcrumb dataclass + to_dict
│   ├── extract.py                          # Parse session transcript → structural fields
│   ├── augment.py                          # Haiku call → 4 interpreted fields
│   ├── push.py                             # Stage + commit + push to claude-journal
│   ├── pull.py                             # Pull claude-journal at session start
│   ├── paths.py                            # Resolve journal repo path, device name, etc.
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── on_stop.py                      # Stop hook entrypoint
│   │   └── on_start.py                     # SessionStart hook entrypoint
│   └── init_device.py                      # First-time setup CLI
├── tests/journal/                          # NEW
│   ├── __init__.py
│   ├── conftest.py                         # Shared fixtures
│   ├── test_breadcrumb.py
│   ├── test_extract.py
│   ├── test_augment.py
│   ├── test_push.py
│   ├── test_pull.py
│   ├── test_init_device.py
│   └── test_e2e.py                         # End-to-end smoke
├── scripts/
│   └── init-journal-device.sh              # NEW — thin wrapper around init_device.py
└── docs/superpowers/
    ├── specs/cognitive-consolidation-design.md   # exists
    └── plans/cognitive-consolidation-phase1.md   # this file
```

**Why pure-Python modules + a thin hook entrypoint:** the hook is shell-callable, but all real logic is in plain Python so we can unit-test it (the hook itself is just `parse stdin → call function → write result`). Matches the existing code style under `src/`.

**Single source of truth for hook code:** `~/.claude/hooks/journal-on-stop.py` is a symlink to `<this-repo>/tools/journal/hooks/on_stop.py`. The init script creates the symlink and registers it in `~/.claude/settings.json`. Pull this repo on a device → hooks update automatically.

---

## Task 1: Set up the `claude-journal` GitHub repo

**Files:** none in this repo. Manual `gh` CLI setup, recorded for reproducibility.

- [ ] **Step 1: Verify `gh` CLI is authenticated**

```bash
gh auth status
```
Expected: `Logged in to github.com as askenter`. If not, run `gh auth login`.

- [ ] **Step 2: Create the private repo and seed the layout**

```bash
gh repo create askenter/claude-journal --private --description "Personal Claude knowledge consolidation hub"
git clone git@github.com:askenter/claude-journal.git ~/claude-journal
cd ~/claude-journal
mkdir -p raw digests memories skills/global skills/projects proposals consolidator/prompts
touch CHANGELOG.md
# .gitkeep so empty directories are tracked
find . -type d \( -name raw -o -name digests -o -name memories -o -name proposals \
  -o -path './skills/global' -o -path './skills/projects' \
  -o -path './consolidator/prompts' \) -exec touch {}/.gitkeep \;
cat > README.md <<'EOF'
# claude-journal

Personal knowledge consolidation hub. Auto-populated by Claude Code hooks on
each device and (eventually) a nightly Claude routine.

Do not edit manually unless you know what you are doing.

Design spec:
specs/cognitive-consolidation-design.md
EOF
git add . && git commit -m "init: bootstrap claude-journal layout"
git push -u origin main
```
Expected: `git status` clean, `gh repo view askenter/claude-journal` shows the repo as private, default branch `main`.

- [ ] **Step 3: Verify repo state**

```bash
gh repo view askenter/claude-journal --json visibility,defaultBranchRef
gh api /repos/askenter/claude-journal/contents/ --jq '.[].name' | sort
```
Expected output of the second command: `CHANGELOG.md README.md consolidator digests memories proposals raw skills`.

- [ ] **Step 4: Commit a marker note in this repo so the design and the journal stay linked**

```bash
cd /home/you/myproject
echo "" >> docs/superpowers/specs/cognitive-consolidation-design.md
echo "## Repo bootstrap" >> docs/superpowers/specs/cognitive-consolidation-design.md
echo "" >> docs/superpowers/specs/cognitive-consolidation-design.md
echo "Live at: https://github.com/askenter/claude-journal (private)" >> docs/superpowers/specs/cognitive-consolidation-design.md
git add docs/superpowers/specs/cognitive-consolidation-design.md
git commit -m "docs(spec): record claude-journal repo as bootstrapped"
```

---

## Task 2: Add Breadcrumb data model with tests

**Files:**
- Create: `tools/journal/__init__.py`
- Create: `tools/journal/breadcrumb.py`
- Create: `tests/journal/__init__.py`
- Create: `tests/journal/conftest.py`
- Create: `tests/journal/test_breadcrumb.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/journal/test_breadcrumb.py
from datetime import datetime, timezone
from tools.journal.breadcrumb import Breadcrumb


def test_structural_only_breadcrumb_serializes():
    bc = Breadcrumb(
        session_id="abc-123",
        device="laptop",
        project="-home-you-myproject",
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
        "project": "-home-you-myproject",
        "started_at": "2026-04-28T09:14:32+00:00",
        "ended_at":   "2026-04-28T10:02:18+00:00",
        "files_touched": ["src/api.py"],
        "skills_invoked": ["superpowers:brainstorming"],
        "first_prompt": "Help me design a memory consolidation pipeline...",
    }


def test_augmented_breadcrumb_includes_synthesized_fields():
    bc = Breadcrumb(
        session_id="abc-123",
        device="laptop",
        project="-home-you-myproject",
        started_at=datetime(2026, 4, 28, 9, 14, 32, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 28, 10, 2, 18, tzinfo=timezone.utc),
        files_touched=[],
        skills_invoked=[],
        first_prompt="...",
        session_summary="Designed pipeline.",
        decisions=["Use claude-journal repo"],
        facts_learned=["Routines run on Anthropic infra"],
        open_questions=[],
    )
    out = bc.to_dict()
    assert out["session_summary"] == "Designed pipeline."
    assert out["decisions"] == ["Use claude-journal repo"]
    assert out["facts_learned"] == ["Routines run on Anthropic infra"]
    assert out["open_questions"] == []


def test_first_prompt_truncated_to_200_chars():
    long = "x" * 500
    bc = Breadcrumb(
        session_id="s", device="d", project="p",
        started_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        files_touched=[], skills_invoked=[], first_prompt=long,
    )
    assert len(bc.to_dict()["first_prompt"]) == 200
```

- [ ] **Step 2: Run tests, verify failure**

```bash
cd /home/you/myproject
PYTHONPATH=. venv/bin/pytest tests/journal/test_breadcrumb.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.journal'`.

- [ ] **Step 3: Implement Breadcrumb**

```python
# tools/journal/__init__.py
"""Cognitive consolidation pipeline: per-device hook utilities."""
```

```python
# tests/journal/__init__.py
```

```python
# tests/journal/conftest.py
import pytest
```

```python
# tools/journal/breadcrumb.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


_FIRST_PROMPT_MAX = 200


@dataclass
class Breadcrumb:
    """One Claude session's breadcrumb. Pushed to claude-journal/raw/.

    Structural fields (top section) are always present.
    Synthesized fields (bottom section) are present only when the Haiku
    augmentation step succeeded — see tools.journal.augment.
    """
    session_id: str
    device: str
    project: str
    started_at: datetime
    ended_at: datetime
    files_touched: list[str]
    skills_invoked: list[str]
    first_prompt: str

    session_summary: Optional[str] = None
    decisions: Optional[list[str]] = None
    facts_learned: Optional[list[str]] = None
    open_questions: Optional[list[str]] = None

    def to_dict(self) -> dict:
        out: dict = {
            "session_id": self.session_id,
            "device": self.device,
            "project": self.project,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "files_touched": self.files_touched,
            "skills_invoked": self.skills_invoked,
            "first_prompt": self.first_prompt[:_FIRST_PROMPT_MAX],
        }
        for key, value in (
            ("session_summary", self.session_summary),
            ("decisions", self.decisions),
            ("facts_learned", self.facts_learned),
            ("open_questions", self.open_questions),
        ):
            if value is not None:
                out[key] = value
        return out
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_breadcrumb.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/journal/__init__.py tools/journal/breadcrumb.py tests/journal/
git commit -m "feat(journal): Breadcrumb data model with optional synthesized fields"
```

---

## Task 3: Implement transcript extraction

The Stop hook receives a JSON payload on stdin from Claude Code. The payload includes (at minimum) `session_id`, `transcript_path`, and `cwd`. We read the JSONL transcript at `transcript_path`, parse tool-use events, and produce the structural breadcrumb fields.

**Files:**
- Create: `tools/journal/extract.py`
- Create: `tests/journal/test_extract.py`
- Create: `tests/journal/fixtures/transcript_simple.jsonl` (test fixture)

- [ ] **Step 1: Write the failing test**

```python
# tests/journal/test_extract.py
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


def test_extract_handles_missing_transcript():
    out = extract_structural(
        session_id="sess-3",
        device="laptop",
        project_dir="/home/you/myproject",
        transcript_path=Path("/nonexistent/transcript.jsonl"),
    )
    assert out["files_touched"] == []
    assert out["first_prompt"] == ""
```

```jsonl
{"type":"user","timestamp":"2026-04-28T09:00:00Z","message":{"content":"Add a new endpoint /feedback to the FastAPI app and wire it in the frontend."}}
{"type":"assistant","timestamp":"2026-04-28T09:01:12Z","message":{"content":[{"type":"tool_use","name":"Skill","input":{"skill":"superpowers:brainstorming"}}]}}
{"type":"assistant","timestamp":"2026-04-28T09:10:05Z","message":{"content":[{"type":"tool_use","name":"Edit","input":{"file_path":"src/api.py"}}]}}
{"type":"assistant","timestamp":"2026-04-28T09:25:45Z","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"frontend/components/Header.tsx"}}]}}
{"type":"assistant","timestamp":"2026-04-28T09:30:00Z","message":{"content":"Done."}}
```

- [ ] **Step 2: Run tests, verify failure**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_extract.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `extract_structural`**

```python
# tools/journal/extract.py
import json
from datetime import datetime
from pathlib import Path

_FIRST_PROMPT_MAX = 200
_TOOLS_THAT_TOUCH_FILES = {"Edit", "Write", "NotebookEdit"}


def _project_key(project_dir: str) -> str:
    """Slugify an absolute path into the auto-memory key format.

    /home/you/myproject -> -home-you-myproject
    """
    return project_dir.replace("/", "-")


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO8601 timestamp, accepting trailing 'Z' for UTC."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def extract_structural(
    *,
    session_id: str,
    device: str,
    project_dir: str,
    transcript_path: Path,
) -> dict:
    """Read a Claude Code session transcript and return the structural
    breadcrumb fields. Tolerant of missing/empty transcripts."""
    files: list[str] = []
    skills: list[str] = []
    first_prompt = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None

    if not Path(transcript_path).exists():
        return _empty(session_id, device, project_dir)

    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_raw = event.get("timestamp")
            if ts_raw:
                ts = _parse_ts(ts_raw)
                if started_at is None:
                    started_at = ts
                ended_at = ts

            if event.get("type") == "user" and not first_prompt:
                content = event.get("message", {}).get("content", "")
                if isinstance(content, str):
                    first_prompt = content[:_FIRST_PROMPT_MAX]

            if event.get("type") == "assistant":
                content = event.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    name = block.get("name")
                    inp = block.get("input", {}) or {}
                    if name in _TOOLS_THAT_TOUCH_FILES:
                        path = inp.get("file_path")
                        if path and path not in files:
                            files.append(path)
                    elif name == "Skill":
                        skill = inp.get("skill")
                        if skill and skill not in skills:
                            skills.append(skill)

    return {
        "session_id": session_id,
        "device": device,
        "project": _project_key(project_dir),
        "started_at": started_at,
        "ended_at": ended_at,
        "files_touched": files,
        "skills_invoked": skills,
        "first_prompt": first_prompt,
    }


def _empty(session_id: str, device: str, project_dir: str) -> dict:
    return {
        "session_id": session_id,
        "device": device,
        "project": _project_key(project_dir),
        "started_at": None,
        "ended_at": None,
        "files_touched": [],
        "skills_invoked": [],
        "first_prompt": "",
    }
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_extract.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/journal/extract.py tests/journal/test_extract.py tests/journal/fixtures/
git commit -m "feat(journal): extract structural breadcrumb fields from session transcript"
```

---

## Task 4: Implement Haiku augmentation with graceful failure

**Files:**
- Create: `tools/journal/augment.py`
- Create: `tests/journal/test_augment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/journal/test_augment.py
from unittest.mock import MagicMock
from tools.journal.augment import augment_with_haiku, AugmentResult


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_augment_returns_synthesized_fields_on_success(monkeypatch):
    fake_text = (
        '{"session_summary":"Designed pipeline.",'
        '"decisions":["Use claude-journal"],'
        '"facts_learned":["Routines run on cloud"],'
        '"open_questions":[]}'
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _mock_response(fake_text)
    monkeypatch.setattr("tools.journal.augment._make_client", lambda: fake_client)

    result = augment_with_haiku(transcript_text="...session content...", model="claude-haiku-4-5-20251001")
    assert isinstance(result, AugmentResult)
    assert result.ok is True
    assert result.session_summary == "Designed pipeline."
    assert result.decisions == ["Use claude-journal"]
    assert result.facts_learned == ["Routines run on cloud"]
    assert result.open_questions == []


def test_augment_returns_failure_on_api_error(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = Exception("network error")
    monkeypatch.setattr("tools.journal.augment._make_client", lambda: fake_client)

    result = augment_with_haiku(transcript_text="...", model="claude-haiku-4-5-20251001")
    assert result.ok is False
    assert result.session_summary is None


def test_augment_returns_failure_on_malformed_json(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _mock_response("not valid json")
    monkeypatch.setattr("tools.journal.augment._make_client", lambda: fake_client)

    result = augment_with_haiku(transcript_text="...", model="claude-haiku-4-5-20251001")
    assert result.ok is False
```

- [ ] **Step 2: Run tests, verify failure**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_augment.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `augment_with_haiku`**

```python
# tools/journal/augment.py
import json
import os
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic


_PROMPT = """\
You are summarizing one Claude Code session for a personal knowledge journal.
Read the session transcript below and return a single JSON object with these
keys:

  - session_summary: one sentence describing what happened
  - decisions: list of one-line decisions made during the session (may be empty)
  - facts_learned: list of one-line non-obvious findings worth remembering
                   (may be empty)
  - open_questions: list of unresolved questions or follow-ups (may be empty)

Output ONLY the JSON object, no prose, no code fences.

Transcript:
---
{transcript}
---
"""


@dataclass
class AugmentResult:
    ok: bool
    session_summary: Optional[str] = None
    decisions: Optional[list[str]] = None
    facts_learned: Optional[list[str]] = None
    open_questions: Optional[list[str]] = None


def _make_client() -> Anthropic:
    return Anthropic()  # picks up ANTHROPIC_API_KEY from env


def augment_with_haiku(
    *,
    transcript_text: str,
    model: str = "claude-haiku-4-5-20251001",
    timeout: float = 15.0,
    max_tokens: int = 800,
) -> AugmentResult:
    """One-shot Haiku call to synthesize four interpreted breadcrumb fields.

    Returns AugmentResult(ok=True, ...) on success, AugmentResult(ok=False)
    on any failure (network, parse, missing key). Never raises.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return AugmentResult(ok=False)

    try:
        client = _make_client()
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            messages=[{
                "role": "user",
                "content": _PROMPT.format(transcript=transcript_text),
            }],
        )
        text = msg.content[0].text.strip()
        data = json.loads(text)
        return AugmentResult(
            ok=True,
            session_summary=data.get("session_summary"),
            decisions=list(data.get("decisions") or []),
            facts_learned=list(data.get("facts_learned") or []),
            open_questions=list(data.get("open_questions") or []),
        )
    except Exception:
        return AugmentResult(ok=False)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_augment.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/journal/augment.py tests/journal/test_augment.py
git commit -m "feat(journal): Haiku breadcrumb augmentation with graceful failure"
```

---

## Task 5: Implement git push helper with offline backlog

The push helper writes the breadcrumb JSON to a buffer file, then attempts to push it to `claude-journal`. On any git failure, the breadcrumb stays in the buffer and the next successful run drains it.

**Files:**
- Create: `tools/journal/paths.py`
- Create: `tools/journal/push.py`
- Create: `tests/journal/test_push.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/journal/test_push.py
import json
from pathlib import Path
from unittest.mock import MagicMock
from tools.journal.push import push_breadcrumb, _drain_buffer


def _make_paths(tmp_path: Path) -> tuple[Path, Path]:
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    (journal / "raw").mkdir()
    buffer = tmp_path / "journal-buffer.jsonl"
    return journal, buffer


def _git_ok(*args, **kwargs):
    result = MagicMock()
    result.returncode = 0
    result.stdout = ""
    result.stderr = ""
    return result


def _git_fail(*args, **kwargs):
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    result.stderr = "git failed"
    return result


def test_push_writes_file_and_succeeds(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    breadcrumb = {
        "session_id": "abc-123",
        "device": "laptop",
        "project": "-home-you-myproject",
        "started_at": "2026-04-28T09:00:00+00:00",
        "ended_at": "2026-04-28T10:00:00+00:00",
    }
    ok = push_breadcrumb(
        breadcrumb=breadcrumb,
        journal_repo=journal,
        buffer_path=buffer,
        date_str="2026-04-28",
    )
    assert ok is True
    assert not buffer.exists() or buffer.read_text() == ""
    target = journal / "raw" / "laptop" / "2026-04-28" / "abc-123.json"
    assert target.exists()
    assert json.loads(target.read_text())["session_id"] == "abc-123"


def test_push_keeps_in_buffer_on_git_failure(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_fail)

    breadcrumb = {"session_id": "abc-123", "device": "laptop"}
    ok = push_breadcrumb(
        breadcrumb=breadcrumb,
        journal_repo=journal,
        buffer_path=buffer,
        date_str="2026-04-28",
    )
    assert ok is False
    assert buffer.exists()
    lines = [json.loads(l) for l in buffer.read_text().splitlines() if l.strip()]
    assert any(l.get("session_id") == "abc-123" for l in lines)


def test_drain_buffer_replays_pending(monkeypatch, tmp_path):
    journal, buffer = _make_paths(tmp_path)
    monkeypatch.setattr("tools.journal.push._run_git", _git_ok)

    pending = [
        {"session_id": "old-1", "device": "laptop"},
        {"session_id": "old-2", "device": "laptop"},
    ]
    buffer.write_text("\n".join(json.dumps(p) for p in pending) + "\n")

    drained = _drain_buffer(buffer=buffer, journal_repo=journal, date_str="2026-04-28")
    assert drained == 2
    assert (journal / "raw" / "laptop" / "2026-04-28" / "old-1.json").exists()
    assert (journal / "raw" / "laptop" / "2026-04-28" / "old-2.json").exists()
    assert buffer.read_text() == ""
```

- [ ] **Step 2: Run tests, verify failure**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_push.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement push helper**

```python
# tools/journal/paths.py
import os
from pathlib import Path


def journal_repo_path() -> Path:
    """Default location of the claude-journal clone."""
    return Path(os.environ.get("CLAUDE_JOURNAL_PATH", str(Path.home() / "claude-journal")))


def buffer_path() -> Path:
    """Local breadcrumb buffer (offline backlog)."""
    return Path(os.environ.get("CLAUDE_JOURNAL_BUFFER", str(Path.home() / ".claude" / "journal-buffer.jsonl")))


def device_name_path() -> Path:
    """Path to the file storing this device's name."""
    return Path.home() / ".claude" / "journal" / "device-name"


def read_device_name() -> str:
    p = device_name_path()
    if not p.exists():
        raise RuntimeError(
            f"device name not found at {p}; run scripts/init-journal-device.sh first"
        )
    return p.read_text().strip()
```

```python
# tools/journal/push.py
import json
import subprocess
from pathlib import Path


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)


def _write_breadcrumb_file(*, breadcrumb: dict, journal_repo: Path, date_str: str) -> Path:
    device = breadcrumb.get("device", "unknown")
    sid = breadcrumb["session_id"]
    target_dir = journal_repo / "raw" / device / date_str
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{sid}.json"
    target.write_text(json.dumps(breadcrumb, indent=2) + "\n")
    return target


def _git_push(journal_repo: Path, msg: str) -> bool:
    pull = _run_git(["git", "pull", "--rebase", "--quiet"], cwd=journal_repo)
    if pull.returncode != 0:
        return False
    add = _run_git(["git", "add", "raw/"], cwd=journal_repo)
    if add.returncode != 0:
        return False
    status = _run_git(["git", "status", "--porcelain"], cwd=journal_repo)
    if not status.stdout.strip():
        return True
    commit = _run_git(["git", "commit", "-m", msg], cwd=journal_repo)
    if commit.returncode != 0:
        return False
    push = _run_git(["git", "push"], cwd=journal_repo)
    return push.returncode == 0


def _append_to_buffer(buffer: Path, breadcrumb: dict) -> None:
    buffer.parent.mkdir(parents=True, exist_ok=True)
    with open(buffer, "a", encoding="utf-8") as f:
        f.write(json.dumps(breadcrumb) + "\n")


def _drain_buffer(*, buffer: Path, journal_repo: Path, date_str: str) -> int:
    """Re-apply buffered breadcrumbs from a previous offline session.

    Returns the number successfully drained. Survivors stay in the buffer.
    """
    if not buffer.exists():
        return 0
    survivors: list[dict] = []
    drained = 0
    for line in buffer.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            bc = json.loads(line)
        except json.JSONDecodeError:
            continue
        _write_breadcrumb_file(breadcrumb=bc, journal_repo=journal_repo, date_str=date_str)
        drained += 1
    if _git_push(journal_repo, f"raw: drain backlog ({drained})"):
        buffer.write_text("")
        return drained
    # push failed — keep all in buffer
    return 0


def push_breadcrumb(
    *,
    breadcrumb: dict,
    journal_repo: Path,
    buffer_path: Path,
    date_str: str,
) -> bool:
    """Stage the breadcrumb and try to push. On failure, append to buffer."""
    try:
        _drain_buffer(buffer=buffer_path, journal_repo=journal_repo, date_str=date_str)
        _write_breadcrumb_file(
            breadcrumb=breadcrumb,
            journal_repo=journal_repo,
            date_str=date_str,
        )
        device = breadcrumb.get("device", "unknown")
        if _git_push(journal_repo, f"raw: {device} {date_str} {breadcrumb['session_id']}"):
            return True
    except Exception:
        pass
    _append_to_buffer(buffer_path, breadcrumb)
    return False
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_push.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/journal/paths.py tools/journal/push.py tests/journal/test_push.py
git commit -m "feat(journal): git push helper with offline backlog and drain"
```

---

## Task 6: Implement Stop hook entrypoint

The Stop hook is invoked by Claude Code on session end. It receives a JSON payload on stdin with `session_id`, `transcript_path`, and `cwd`. It must complete in well under 30s and never block the user; failures are swallowed.

**Files:**
- Create: `tools/journal/hooks/__init__.py`
- Create: `tools/journal/hooks/on_stop.py`
- Create: `tests/journal/test_on_stop.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/journal/test_on_stop.py
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
from tools.journal.hooks import on_stop


def test_on_stop_happy_path(monkeypatch, tmp_path, capsys):
    # Arrange a fake transcript and journal repo on disk
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type":"user","timestamp":"2026-04-28T09:00:00Z","message":{"content":"Do thing."}}\n'
        '{"type":"assistant","timestamp":"2026-04-28T09:30:00Z","message":{"content":[{"type":"tool_use","name":"Edit","input":{"file_path":"src/api.py"}}]}}\n'
    )
    journal = tmp_path / "claude-journal"
    (journal / "raw").mkdir(parents=True)
    buffer = tmp_path / "journal-buffer.jsonl"
    device_name_file = tmp_path / "device-name"
    device_name_file.write_text("laptop\n")

    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)
    monkeypatch.setattr("tools.journal.paths.buffer_path", lambda: buffer)
    monkeypatch.setattr("tools.journal.paths.device_name_path", lambda: device_name_file)

    fake_augment = MagicMock(return_value=MagicMock(
        ok=True,
        session_summary="Did the thing.",
        decisions=[],
        facts_learned=[],
        open_questions=[],
    ))
    monkeypatch.setattr("tools.journal.hooks.on_stop.augment_with_haiku", fake_augment)

    fake_push = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.hooks.on_stop.push_breadcrumb", fake_push)

    # Act
    payload = {
        "session_id": "sess-1",
        "transcript_path": str(transcript),
        "cwd": "/home/you/myproject",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = on_stop.main()

    # Assert
    assert rc == 0
    fake_push.assert_called_once()
    sent = fake_push.call_args.kwargs["breadcrumb"]
    assert sent["session_id"] == "sess-1"
    assert sent["device"] == "laptop"
    assert sent["project"] == "-home-you-myproject"
    assert sent["session_summary"] == "Did the thing."
    assert sent["files_touched"] == ["src/api.py"]


def test_on_stop_swallows_all_exceptions(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    # Should not raise; should return 0
    rc = on_stop.main()
    assert rc == 0
```

- [ ] **Step 2: Run tests, verify failure**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_on_stop.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the hook**

```python
# tools/journal/hooks/__init__.py
```

```python
# tools/journal/hooks/on_stop.py
"""Stop hook entrypoint. Invoked by Claude Code at session end.

Reads a JSON payload on stdin, builds a breadcrumb, and pushes it to
claude-journal. Always exits 0 so it never blocks the user.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.journal.augment import augment_with_haiku
from tools.journal.breadcrumb import Breadcrumb
from tools.journal.extract import extract_structural
from tools.journal.paths import (
    buffer_path,
    journal_repo_path,
    read_device_name,
)
from tools.journal.push import push_breadcrumb


def _read_payload() -> dict:
    return json.loads(sys.stdin.read())


def _build_breadcrumb(payload: dict, device: str) -> Breadcrumb:
    structural = extract_structural(
        session_id=payload["session_id"],
        device=device,
        project_dir=payload.get("cwd", str(Path.cwd())),
        transcript_path=Path(payload["transcript_path"]),
    )
    started = structural["started_at"] or datetime.now(timezone.utc)
    ended = structural["ended_at"] or datetime.now(timezone.utc)

    transcript_text = ""
    try:
        transcript_text = Path(payload["transcript_path"]).read_text(encoding="utf-8")[-50_000:]
    except Exception:
        pass

    aug = augment_with_haiku(transcript_text=transcript_text)
    bc = Breadcrumb(
        session_id=structural["session_id"],
        device=structural["device"],
        project=structural["project"],
        started_at=started,
        ended_at=ended,
        files_touched=structural["files_touched"],
        skills_invoked=structural["skills_invoked"],
        first_prompt=structural["first_prompt"],
        session_summary=aug.session_summary if aug.ok else None,
        decisions=aug.decisions if aug.ok else None,
        facts_learned=aug.facts_learned if aug.ok else None,
        open_questions=aug.open_questions if aug.ok else None,
    )
    return bc


def main() -> int:
    try:
        payload = _read_payload()
        device = read_device_name()
        bc = _build_breadcrumb(payload, device)
        date_str = bc.started_at.strftime("%Y-%m-%d")
        push_breadcrumb(
            breadcrumb=bc.to_dict(),
            journal_repo=journal_repo_path(),
            buffer_path=buffer_path(),
            date_str=date_str,
        )
    except Exception as exc:
        try:
            log = Path.home() / ".claude" / "journal-buffer.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now(timezone.utc).isoformat()}] on_stop error: {exc!r}\n")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_on_stop.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/journal/hooks/__init__.py tools/journal/hooks/on_stop.py tests/journal/test_on_stop.py
git commit -m "feat(journal): Stop hook entrypoint with end-to-end breadcrumb push"
```

---

## Task 7: Implement SessionStart hook (pull-only for Phase 1)

The SessionStart hook pulls the latest `claude-journal` so other devices' breadcrumbs are visible locally. In Phase 2 it will gain memory/skill sync; in Phase 3 it will surface proposals. For Phase 1 it's deliberately minimal — but the entrypoint exists.

**Files:**
- Create: `tools/journal/pull.py`
- Create: `tools/journal/hooks/on_start.py`
- Create: `tests/journal/test_on_start.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/journal/test_on_start.py
import io
import json
from unittest.mock import MagicMock
from tools.journal.hooks import on_start


def test_on_start_pulls_repo(monkeypatch, tmp_path):
    journal = tmp_path / "claude-journal"
    journal.mkdir()
    monkeypatch.setattr("tools.journal.paths.journal_repo_path", lambda: journal)

    fake_pull = MagicMock(return_value=True)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", fake_pull)

    payload = {"session_id": "sess-1", "cwd": "/home/you/myproject"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = on_start.main()

    assert rc == 0
    fake_pull.assert_called_once()


def test_on_start_swallows_pull_failure(monkeypatch):
    fake_pull = MagicMock(return_value=False)
    monkeypatch.setattr("tools.journal.hooks.on_start.pull_journal", fake_pull)

    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    rc = on_start.main()
    assert rc == 0
```

- [ ] **Step 2: Run tests, verify failure**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_on_start.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement pull + on_start**

```python
# tools/journal/pull.py
from pathlib import Path
from tools.journal.push import _run_git


def pull_journal(journal_repo: Path) -> bool:
    """Best-effort pull. Returns True iff the pull succeeded."""
    if not (journal_repo / ".git").exists():
        return False
    result = _run_git(["git", "pull", "--rebase", "--quiet"], cwd=journal_repo)
    return result.returncode == 0
```

```python
# tools/journal/hooks/on_start.py
"""SessionStart hook entrypoint. Pulls claude-journal so this device sees
other devices' work. Phase 1 is pull-only; Phase 2 adds memory/skill sync;
Phase 3 adds proposal surfacing."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.journal.paths import journal_repo_path
from tools.journal.pull import pull_journal


def _read_payload_safe() -> dict:
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def main() -> int:
    try:
        _ = _read_payload_safe()  # payload not used in Phase 1
        pull_journal(journal_repo_path())
    except Exception as exc:
        try:
            log = Path.home() / ".claude" / "journal-buffer.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now(timezone.utc).isoformat()}] on_start error: {exc!r}\n")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_on_start.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/journal/pull.py tools/journal/hooks/on_start.py tests/journal/test_on_start.py
git commit -m "feat(journal): SessionStart hook (pull-only for Phase 1)"
```

---

## Task 8: Implement device init script

The init script is run once per device. It:
1. Validates that `~/claude-journal` is a clone of the right repo (clones it if missing).
2. Records the device name to `~/.claude/journal/device-name`.
3. Symlinks `~/.claude/hooks/journal-on-stop.py` and `journal-on-start.py` to this repo's modules so updates propagate via `git pull`.
4. Updates `~/.claude/settings.json` to register the hooks under the `Stop` and `SessionStart` events (idempotent — does nothing if already registered).

**Files:**
- Create: `tools/journal/init_device.py`
- Create: `tests/journal/test_init_device.py`
- Create: `scripts/init-journal-device.sh`

- [ ] **Step 1: Write the failing test**

```python
# tests/journal/test_init_device.py
import json
from pathlib import Path
from tools.journal.init_device import register_hooks_in_settings


def test_register_hooks_creates_settings(tmp_path):
    settings = tmp_path / "settings.json"
    on_stop = tmp_path / "on_stop.py"
    on_start = tmp_path / "on_start.py"

    register_hooks_in_settings(
        settings_path=settings,
        on_stop_path=on_stop,
        on_start_path=on_start,
    )
    data = json.loads(settings.read_text())
    stop_cmds = [h["command"] for h in data["hooks"]["Stop"][0]["hooks"]]
    start_cmds = [h["command"] for h in data["hooks"]["SessionStart"][0]["hooks"]]
    assert str(on_stop) in stop_cmds
    assert str(on_start) in start_cmds


def test_register_hooks_is_idempotent(tmp_path):
    settings = tmp_path / "settings.json"
    on_stop = tmp_path / "on_stop.py"
    on_start = tmp_path / "on_start.py"

    register_hooks_in_settings(settings_path=settings, on_stop_path=on_stop, on_start_path=on_start)
    register_hooks_in_settings(settings_path=settings, on_stop_path=on_stop, on_start_path=on_start)
    data = json.loads(settings.read_text())
    stop_hooks = data["hooks"]["Stop"][0]["hooks"]
    matching = [h for h in stop_hooks if h.get("command") == str(on_stop)]
    assert len(matching) == 1


def test_register_hooks_preserves_existing_unrelated(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "theme": "dark",
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "/some/other/hook.sh"}]}]
        }
    }))
    on_stop = tmp_path / "on_stop.py"
    on_start = tmp_path / "on_start.py"
    register_hooks_in_settings(settings_path=settings, on_stop_path=on_stop, on_start_path=on_start)

    data = json.loads(settings.read_text())
    assert data["theme"] == "dark"
    cmds = [h["command"] for h in data["hooks"]["Stop"][0]["hooks"]]
    assert "/some/other/hook.sh" in cmds
    assert str(on_stop) in cmds
```

- [ ] **Step 2: Run tests, verify failure**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_init_device.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement init_device**

```python
# tools/journal/init_device.py
"""First-time per-device setup for the journal pipeline."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def register_hooks_in_settings(
    *,
    settings_path: Path,
    on_stop_path: Path,
    on_start_path: Path,
) -> None:
    """Insert the journal hooks into Claude Code's settings.json idempotently."""
    if settings_path.exists():
        data = json.loads(settings_path.read_text())
    else:
        data = {}
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    hooks = data.setdefault("hooks", {})
    for event, path in (("Stop", on_stop_path), ("SessionStart", on_start_path)):
        groups = hooks.setdefault(event, [])
        if not groups:
            groups.append({"hooks": []})
        existing_cmds = {h.get("command") for g in groups for h in g.get("hooks", [])}
        if str(path) in existing_cmds:
            continue
        groups[0]["hooks"].append({"type": "command", "command": str(path)})

    settings_path.write_text(json.dumps(data, indent=2) + "\n")


def _ensure_journal_clone(repo_url: str, target: Path) -> None:
    if target.exists() and (target / ".git").exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", repo_url, str(target)], check=True)


def _write_device_name(device: str) -> None:
    p = Path.home() / ".claude" / "journal" / "device-name"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(device + "\n")


def _symlink(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(src)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize this device for the journal pipeline.")
    parser.add_argument("device", help="Stable name for this device (e.g., laptop, workstation).")
    parser.add_argument(
        "--repo-url",
        default="git@github.com:askenter/claude-journal.git",
        help="claude-journal git URL.",
    )
    parser.add_argument(
        "--journal-path",
        default=str(Path.home() / "claude-journal"),
        help="Local path for the claude-journal clone.",
    )
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[2]
    on_stop_src = project_root / "tools" / "journal" / "hooks" / "on_stop.py"
    on_start_src = project_root / "tools" / "journal" / "hooks" / "on_start.py"
    on_stop_dst = Path.home() / ".claude" / "hooks" / "journal-on-stop.py"
    on_start_dst = Path.home() / ".claude" / "hooks" / "journal-on-start.py"

    _ensure_journal_clone(args.repo_url, Path(args.journal_path))
    _write_device_name(args.device)
    _symlink(on_stop_src, on_stop_dst)
    _symlink(on_start_src, on_start_dst)
    register_hooks_in_settings(
        settings_path=Path.home() / ".claude" / "settings.json",
        on_stop_path=on_stop_dst,
        on_start_path=on_start_dst,
    )
    print(f"journal device '{args.device}' initialized.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```bash
# scripts/init-journal-device.sh
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${HERE}/venv/bin/python" -m tools.journal.init_device "$@"
```

After creating, mark executable:
```bash
chmod +x scripts/init-journal-device.sh
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=. venv/bin/pytest tests/journal/test_init_device.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/journal/init_device.py scripts/init-journal-device.sh tests/journal/test_init_device.py
git commit -m "feat(journal): init-journal-device script with idempotent hook registration"
```

---

## Task 9: End-to-end smoke test on this dev box

Validates the full pipeline runs against the real GitHub repo from this device.

**Files:** none new; manual verification.

- [ ] **Step 1: Run all unit tests**

```bash
cd /home/you/myproject
PYTHONPATH=. venv/bin/pytest tests/journal/ -v
```
Expected: all passing (16+ tests across the 8 test modules above).

- [ ] **Step 2: Initialize this device**

```bash
./scripts/init-journal-device.sh bot_dev1
```
Expected:
- `~/claude-journal/.git` exists
- `~/.claude/journal/device-name` contains `bot_dev1`
- `~/.claude/hooks/journal-on-stop.py` is a symlink to `tools/journal/hooks/on_stop.py`
- `~/.claude/hooks/journal-on-start.py` is a symlink to `tools/journal/hooks/on_start.py`
- `~/.claude/settings.json` has both hooks registered under `Stop` and `SessionStart`

- [ ] **Step 3: Smoke-test the Stop hook with a synthetic payload**

```bash
# Use the most recent transcript from this project
LATEST_TRANSCRIPT=$(ls -t ~/.claude/projects/-home-you-myproject/*.jsonl 2>/dev/null | head -1)
SID=$(basename "$LATEST_TRANSCRIPT" .jsonl)

PAYLOAD=$(jq -nc \
  --arg sid "$SID" \
  --arg t "$LATEST_TRANSCRIPT" \
  '{session_id: $sid, transcript_path: $t, cwd: "/home/you/myproject"}')

echo "$PAYLOAD" | PYTHONPATH=/home/you/myproject \
  /home/you/myproject/venv/bin/python /home/you/myproject/tools/journal/hooks/on_stop.py
```
Expected: command exits 0 within ~5–10 seconds (the Haiku call dominates).

- [ ] **Step 4: Verify a breadcrumb landed in the repo**

```bash
cd ~/claude-journal && git pull --quiet
TODAY=$(date -u +%Y-%m-%d)
ls raw/bot_dev1/$TODAY/
```
Expected: at least one `<sid>.json` file. Inspect:
```bash
cat raw/bot_dev1/$TODAY/*.json | head -50
```
Should show structural fields plus (if Haiku succeeded) `session_summary`, `decisions`, `facts_learned`, `open_questions`.

- [ ] **Step 5: Verify SessionStart hook pulls without error**

```bash
echo '{"session_id":"smoke","cwd":"/home/you/myproject"}' | \
  PYTHONPATH=/home/you/myproject \
  /home/you/myproject/venv/bin/python /home/you/myproject/tools/journal/hooks/on_start.py
```
Expected: exit 0, no output, `~/claude-journal` is up to date with origin.

- [ ] **Step 6: Verify offline-backlog behavior**

```bash
# Temporarily break git push by setting an invalid remote
cd ~/claude-journal
git remote set-url origin git@github.com:invalid/invalid.git

# Re-run the Stop hook smoke test
echo "$PAYLOAD" | PYTHONPATH=/home/you/myproject \
  /home/you/myproject/venv/bin/python /home/you/myproject/tools/journal/hooks/on_stop.py

# Confirm the breadcrumb is buffered
cat ~/.claude/journal-buffer.jsonl | head -5

# Restore the remote
git remote set-url origin git@github.com:askenter/claude-journal.git

# Re-run; backlog should drain
echo "$PAYLOAD" | PYTHONPATH=/home/you/myproject \
  /home/you/myproject/venv/bin/python /home/you/myproject/tools/journal/hooks/on_stop.py

# Buffer should now be empty
cat ~/.claude/journal-buffer.jsonl
```
Expected: buffer fills on push failure, drains on next successful push.

- [ ] **Step 7: Commit acceptance evidence**

```bash
cd /home/you/myproject
echo "Phase 1 acceptance smoke completed on $(date -Iseconds) by $(whoami)@$(hostname)" \
  >> docs/superpowers/plans/cognitive-consolidation-phase1.md
git add docs/superpowers/plans/cognitive-consolidation-phase1.md
git commit -m "docs(plan): record Phase 1 acceptance smoke run"
```

---

## Phase 1 acceptance criteria (subset of full spec)

The following must hold for Phase 1 to be considered complete:

1. `claude-journal` repo exists, private, with the spec layout.
2. `~/.claude/settings.json` registers both hooks via the init script.
3. `~/.claude/hooks/journal-on-stop.py` and `journal-on-start.py` are symlinks back into this repo.
4. The Stop hook produces a valid breadcrumb on `raw/<device>/<date>/<sid>.json` when fed a real transcript.
5. The Haiku augmentation step is best-effort: structural breadcrumb still pushes when the API call fails.
6. The offline backlog (buffer file) fills on git failure and drains on next successful push.
7. SessionStart hook performs `git pull --rebase` on `claude-journal` and exits 0 even on pull failure.
8. All Phase 1 unit tests pass: `PYTHONPATH=. venv/bin/pytest tests/journal/ -v`.

Items deferred to later phases — explicitly NOT required for Phase 1 acceptance:
- Memory/skill sync at SessionStart
- Morning digest output
- Proposal queue
- Central consolidator routine
- `/journal` and `/consolidate-now` slash commands
- CHANGELOG entries

---

## Notes for the implementer

- **Use the venv:** `venv/bin/python` and `venv/bin/pytest`. Never run with system Python.
- **Anthropic SDK version:** the `anthropic` package is already in `requirements.txt` for the chatbot; if not pinned at `>=0.40`, bump it. The `messages.create(timeout=...)` parameter exists on recent versions.
- **Network egress:** the Stop hook needs outbound HTTPS to `api.anthropic.com` and SSH (or HTTPS) to `github.com`. Both are typically open, but if the dev box restricts them, the hook degrades gracefully (Haiku failure → structural-only breadcrumb; git failure → buffered).
- **Don't enable hooks on shared servers:** the hook reads conversation transcripts and pushes them to a private repo. That's fine on a personal dev box, not on a shared bastion. If `~/.claude/settings.json` is shared somehow, gate registration behind a per-host setting.
- **Sensitive data:** Phase 1 ships breadcrumbs unredacted. If a transcript contains a secret, it lands in `claude-journal`. Repo is private; v2 will add a redaction pass in `extract.py`.
