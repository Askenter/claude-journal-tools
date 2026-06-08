# Skill Proposals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route net-new distilled skills through the `/journal accept|skip|edit` proposal queue instead of silently auto-applying them, and make every skill's lifecycle plainly visible in the data repo via a `CHANGELOG.md` ledger and a `skills/INDEX.md` manifest.

**Architecture:** Device-side, the only new *code* is per-entry type labeling in `surface_proposals.py` (so a `## New skill:` proposal surfaces tagged "new skill"). The `/journal` skill (prose) gains a new-skill accept/skip/edit branch that installs the skill into the data repo's `skills/` tree, mirrors it locally, and hand-maintains the ledger + manifest using exact documented formats. The canonical design spec is updated so each per-user consolidator `ROUTINE.md` emits skill proposals instead of auto-writing skills. No Python helper is shipped: a plugin SKILL.md cannot reliably invoke a bundled script (`${CLAUDE_PLUGIN_ROOT}` is exported only to hook/MCP/LSP processes), so the ledger/manifest are line-oriented formats maintained by hand on both sides.

**Tech Stack:** Python 3.11+ (stdlib only; runtime hooks/tools run under system `python3`), pytest (via `venv/bin/python`), Markdown (skill + spec docs).

**Design spec:** `docs/specs/2026-06-08-skill-proposals-design.md`

**Test command (whole suite):** `venv/bin/python -m pytest tests/ -q` (must stay green; currently 97 passing).

---

### Task 1: Per-entry proposal labeling in `surface_proposals.py`

Surfacing currently emits one summary line per proposal *file*. Change it to emit one line per `## ` *entry*, each tagged with its type (`new skill` / `feedback rule` / `CLAUDE.md edit` / `proposal`), and broaden the standing blurb to mention new skills. Project-key filtering is unchanged.

**Files:**
- Modify: `tools/journal/surface_proposals.py` (full rewrite of the module body below)
- Test: `tests/journal/test_surface_proposals.py` (add two tests)

- [ ] **Step 1: Write the failing tests**

Append these two tests to `tests/journal/test_surface_proposals.py`:

```python
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
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `venv/bin/python -m pytest tests/journal/test_surface_proposals.py -q`
Expected: the two new tests FAIL (current output has no `[new skill]` tag — it emits ``- `<path>` — <summary>`` lines). Existing tests still pass.

- [ ] **Step 3: Rewrite `tools/journal/surface_proposals.py`**

Replace the **entire** file with:

```python
"""Surface pending journal proposals to Claude via SessionStart's
`additionalContext`.

The central routine writes proposals (Track 1b feedback memories, Track 2
new-skill suggestions, Track 3 CLAUDE.md edits) under
`<journal>/proposals/<date>-<project>.md`. On SessionStart for that project,
we want the next assistant turn to see them so the user can act via
`/journal accept|skip|edit`.

We build a short markdown block listing the pending proposals for the current
project — one line per `## ` entry, each tagged with its type (new skill /
feedback rule / CLAUDE.md edit) — and return it as the
hookSpecificOutput.additionalContext value (read by Claude Code from the
hook's stdout).

Proposal filenames follow `<YYYY-MM-DD>-<project-key>.md`. The current
project's key comes from the SessionStart payload's `cwd` (replace `/`
with `-`, matching the breadcrumb extractor).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def project_key_from_cwd(cwd: str) -> str:
    """Mirror the project-key derivation used by the Stop hook so proposal
    files land under the same key the breadcrumbs use."""
    return cwd.replace("/", "-")


def _list_proposals_for_project(proposals_dir: Path, project_key: str) -> list[Path]:
    if not proposals_dir.exists():
        return []
    matches: list[Path] = []
    for path in sorted(proposals_dir.glob("*.md")):
        # Filename is "<YYYY-MM-DD>-<project>.md"
        stem = path.stem  # without .md
        if stem.endswith("-" + project_key) or stem == project_key:
            matches.append(path)
    return matches


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _first_nonempty(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _iter_entries(text: str) -> list[tuple[str, str]]:
    """Split a proposal file into (heading, entry_text) pairs by `## `
    headings. Any content before the first heading is ignored."""
    entries: list[tuple[str, list[str]]] = []
    current: Optional[tuple[str, list[str]]] = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                entries.append(current)
            current = (line[3:].strip(), [line])
        elif current is not None:
            current[1].append(line)
    if current is not None:
        entries.append(current)
    return [(heading, "\n".join(body)) for heading, body in entries]


def _entry_label(heading: str, body: str) -> str:
    """Classify one proposal entry for display."""
    h = heading.lower()
    b = body.lower()
    if h.startswith("new skill") or "kind: new-skill" in b or "kind:** new-skill" in b:
        return "new skill"
    if "feedback" in h or "type: feedback" in b:
        return "feedback rule"
    if "claude.md" in h or "claude.md" in b or "target:" in b:
        return "CLAUDE.md edit"
    return "proposal"


def build_proposal_context(*, journal_repo: Path, cwd: str) -> Optional[str]:
    """Return the additionalContext string to surface, or None if there
    are no pending proposals for this project."""
    project_key = project_key_from_cwd(cwd)
    proposals = _list_proposals_for_project(journal_repo / "proposals", project_key)
    if not proposals:
        return None
    lines = [
        "📓 claude-journal has pending proposals for this project:",
        "",
    ]
    for path in proposals:
        text = _read_text(path)
        entries = _iter_entries(text)
        if not entries:
            summary = _first_nonempty(text) or path.name
            lines.append(f"- [proposal] {summary} (`{path}`)")
            continue
        for heading, body in entries:
            label = _entry_label(heading, body)
            lines.append(f"- [{label}] {heading} (`{path}`)")
    lines.extend([
        "",
        "These are new skills, behavioral rules, or CLAUDE.md edits the "
        "consolidator extracted from recent sessions. They are NOT "
        "auto-applied.",
        "",
        "Run `/journal accept`, `/journal skip`, or `/journal edit` to "
        "review and act on them.",
    ])
    return "\n".join(lines)
```

- [ ] **Step 4: Run the full surface_proposals test file to verify all pass**

Run: `venv/bin/python -m pytest tests/journal/test_surface_proposals.py -q`
Expected: PASS — both new tests plus all 6 pre-existing tests (the pre-existing ones still match: filenames and first-heading text still appear in the output; `/journal accept|skip|edit` still advertised; other-project files still filtered out).

- [ ] **Step 5: Run the whole suite to confirm no regressions**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: PASS, 99 tests (97 prior + 2 new).

- [ ] **Step 6: Commit**

```bash
git add tools/journal/surface_proposals.py tests/journal/test_surface_proposals.py
git commit -m "feat(journal): label proposal entries by type, surface new-skill proposals"
```

---

### Task 2: New-skill accept/skip/edit branch in the `/journal` skill

Teach the `/journal` skill to recognize `## New skill:` entries and handle them: on accept install the skill + record `accepted`; on skip record `skipped`; commit the journal repo including `skills/`, `CHANGELOG.md`, and `skills/INDEX.md`. This is a prose skill (no unit test); verification is a careful re-read plus confirming the suite is unaffected.

**Files:**
- Modify: `skills/journal/SKILL.md`

- [ ] **Step 1: Extend the "Read each proposal file" list (step 2 of the skill) to three shapes**

In `skills/journal/SKILL.md`, replace:

```
2. **Read each proposal file.** Each contains one or more entries
   delimited by `## ` headings. Entries are typically of two shapes:

   - **feedback proposal** — contains a fenced markdown block with
     frontmatter `type: feedback`. The `body` is a behavioral rule the
     user has expressed in some recent session.
   - **CLAUDE.md edit proposal** — contains a target file path and either
     a unified diff or a prose change request.
```

with:

```
2. **Read each proposal file.** Each contains one or more entries
   delimited by `## ` headings. Entries are of three shapes:

   - **feedback proposal** — contains a fenced markdown block with
     frontmatter `type: feedback`. The `body` is a behavioral rule the
     user has expressed in some recent session.
   - **CLAUDE.md edit proposal** — contains a target file path and either
     a unified diff or a prose change request.
   - **new-skill proposal** — heading `## New skill: <name>`, with a
     `kind: new-skill` marker, a `scope:` (`global` or `project:<key>`), a
     `target:` path under `skills/`, a `provenance:` line, a rationale, and
     the full `SKILL.md` wrapped in a **four-backtick fence** (so a skill
     body containing its own ``` blocks round-trips intact).
```

- [ ] **Step 2: Add the new-skill `accept` handling**

In the `- **`accept`:**` block, after the `For CLAUDE.md edits:` bullet, add:

```
     - For new-skill proposals:
       1. Parse `scope`, `target`, the skill `<name>` (from the heading),
          the one-line `description` (from the fenced skill's frontmatter),
          and the `provenance` line. Extract the `SKILL.md` body from inside
          the four-backtick fence.
       2. Write that body to `~/claude-journal/<target>` (create parent
          dirs). If a skill named `<name>` already exists there, show the
          user and ask before overwriting.
       3. Mirror it onto this device so no manual install is needed — copy
          the whole skill directory:
            - `scope: global` → `~/.claude/skills/<name>/`
            - `scope: project:<key>` →
              `~/.claude/projects/<key>/.claude/skills/<name>/`
          Other devices receive it via their next SessionStart `sync_skills`
          sync. (Claude Code enumerates skills at session start, so an
          accepted skill is invocable from the next session.)
       4. Record the acceptance in the data repo by hand, in two files
          (`<today>` = UTC date, e.g. `date -u +%F`):
            - append one line to `~/claude-journal/CHANGELOG.md`:
              `<today> +skill accepted <scope>/<name>`
            - in `~/claude-journal/skills/INDEX.md`, find the row whose
              Skill = `<name>` and Scope = `<scope>` and change its Status
              from `proposed` to `accepted`, setting Updated = `<today>`. If
              no such row exists (proposal predates the manifest, or the file
              is missing), create the manifest from the header below and add:
              `| <name> | <scope> | accepted | <description> | <provenance> | <today> |`
       5. Remove this new-skill entry from the proposal file.
```

- [ ] **Step 3: Add the new-skill `skip` handling**

Replace the `skip` bullet:

```
   - **`skip`:** delete the proposal file from `~/claude-journal/proposals/`
     without applying anything. The user is dismissing it permanently.
```

with:

```
   - **`skip`:** the user is dismissing the pending proposals permanently.
     Before removing them, for **each new-skill entry** in the affected
     proposal file(s), record the skip in the data repo (`<today>` =
     `date -u +%F`):
       - append to `~/claude-journal/CHANGELOG.md`:
         `<today> -skill skipped <scope>/<name>`
       - remove that skill's row (Skill = `<name>`, Scope = `<scope>`) from
         `~/claude-journal/skills/INDEX.md`.
     Feedback and CLAUDE.md-edit entries need no record-keeping on skip.
     Then delete the proposal file(s) from `~/claude-journal/proposals/`.
```

- [ ] **Step 4: Document the data-repo record formats (new section before "## Guardrails")**

Insert this section immediately before `## Guardrails`:

````
## Data-repo skill record formats

Keep both files in lockstep with accept/skip so a skill's lifecycle is plainly
visible. These are maintained by hand — match the formats exactly.

**`~/claude-journal/CHANGELOG.md`** — append one dated line per event:

```
2026-06-08 ~skill proposed global/condition-based-waiting — distilled from 2 sessions on 2026-06-05, 2026-06-07
2026-06-09 +skill accepted global/condition-based-waiting
2026-06-09 -skill skipped  project:-home-opc-ASEP/flaky-retry
```

`~` proposed (written by the consolidator), `+` accepted, `-` skipped. If the
file is missing, create it with a `# Changelog` heading first.

**`~/claude-journal/skills/INDEX.md`** — one row per proposed/accepted skill:

```
# Skills index

Current status of distilled skills. Maintained by the consolidator (proposed)
and `/journal` (accepted; skip removes the row).

| Skill | Scope | Status | Description | Provenance | Updated |
|---|---|---|---|---|---|
| condition-based-waiting | global | accepted | Wait on a condition, never a sleep | 2 sessions: 2026-06-05, 2026-06-07 | 2026-06-09 |
```

Accept flips the row's Status to `accepted`; skip removes the row. Keep cell
values free of `|` and newlines.
````

- [ ] **Step 5: Update the commit step (step 4 of the skill) to stage the new files**

Replace:

```
4. **Commit and push the change in `~/claude-journal/`** so other devices
   see that the proposal has been resolved (file removed). Use a commit
   message like `proposal: <action> <date>-<project-key>` and `git push`.
```

with:

```
4. **Commit and push the change in `~/claude-journal/`** so other devices
   see that the proposal has been resolved. Stage everything the action
   touched — the proposal change, and (for accepted/skipped skills) the new
   `skills/<scope>/<name>/` files, `CHANGELOG.md`, and `skills/INDEX.md`. Use
   a commit message like `proposal: <action> <date>-<project-key>` and
   `git push`.
```

- [ ] **Step 6: Verify the skill reads coherently and the suite is unaffected**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: PASS, 99 tests (unchanged — this task edits prose only).
Then re-read `skills/journal/SKILL.md` end-to-end and confirm: three entry shapes described; accept/skip/edit each handle new-skill entries; the record formats section matches the CHANGELOG/INDEX lines referenced in accept/skip; no dangling reference to a Python helper.

- [ ] **Step 7: Commit**

```bash
git add skills/journal/SKILL.md
git commit -m "feat(journal): handle new-skill proposals in /journal accept|skip|edit"
```

---

### Task 3: Update the canonical design spec (Track 2 → proposal queue)

Bring `docs/specs/cognitive-consolidation-design.md` in line so each per-user consolidator `ROUTINE.md` emits skill *proposals* (plus the ledger + manifest) instead of auto-writing skills. Also commit the feature design spec.

**Files:**
- Modify: `docs/specs/cognitive-consolidation-design.md`
- Add: `docs/specs/2026-06-08-skill-proposals-design.md` (already written this session)

- [ ] **Step 1: Rewrite the Track 2 section**

Replace the whole `### Track 2 — Skills (tier-2: auto-apply, log to CHANGELOG)` section (from that heading down to, and including, the `**Out of scope for tier 2:**` paragraph) with:

```
### Track 2 — New skills (proposal queue, ledger + manifest)

**Trigger threshold:** a technique becomes a candidate skill only when at
least **2 sessions on different days** referenced it. Borrowed from
`superpowers:writing-skills` ("create when you'd reference this again across
projects"). Frequency filter prevents one-off solutions from being canonized.

**Output (a proposal, not an auto-applied skill):** the routine writes the
new skill as a `## New skill: <name>` entry inside the per-project proposal
file `proposals/<date>-<project-key>.md` — the same file Track 1b/Track 3
use. The entry carries `kind: new-skill`, a `scope:` (`global` or
`project:<key>`), a `target:` path under `skills/`, a provenance line, a
rationale, and the full `SKILL.md` wrapped in a four-backtick fence. A
global-scope skill is filed under the project whose breadcrumbs produced it
(most recent if several) so it surfaces when the user next opens that
project; the `scope` tag — not the filename — decides where `accept`
installs it.

**Record (so the lifecycle is plainly visible):** at the same time, the
routine appends a `~skill proposed <scope>/<name> — <provenance>` line to
`CHANGELOG.md` and inserts a `proposed` row into `skills/INDEX.md` (a
manifest table: Skill | Scope | Status | Description | Provenance | Updated).

**Surfacing + resolution:** the SessionStart hook surfaces the entry tagged
"new skill"; the user runs `/journal accept|skip|edit`. On accept, `/journal`
writes the `SKILL.md` into `skills/<scope>/<name>/`, mirrors it onto the
device, flips the CHANGELOG/INDEX records to `accepted`, and pushes — other
devices then receive it via the existing SessionStart `sync_skills` sync. On
skip, `/journal` records `-skill skipped` and removes the INDEX row.

**Why a proposal, not auto-apply:** a new skill is description-gated, but it
still loads behavior the user never reviewed. Routing it through the same
review gate as feedback memories and CLAUDE.md edits keeps the user in
control; the CHANGELOG + INDEX give an at-a-glance audit trail.

**Out of scope for Track 2:** edits to *existing* skills. Those go through
Track 3 (proposals) because they change behavior of code that already fires.
```

- [ ] **Step 2: Update acceptance criterion #3**

Replace:

```
3. The SessionStart hook applies track-1a memories (`user`, `project`,
   `reference`) and track-2 skills silently, surfaces track-1b
   (`feedback`-memory) proposals and track-3 (CLAUDE.md / existing-skill)
   proposals as inline system-reminders, and emits the morning digest line
   when applicable.
```

with:

```
3. The SessionStart hook applies track-1a memories (`user`, `project`,
   `reference`) silently, surfaces track-1b (`feedback`-memory), track-2
   (new-skill), and track-3 (CLAUDE.md / existing-skill) proposals as inline
   system-reminders tagged by type, and emits the morning digest line when
   applicable. Newly *accepted* skills sync silently thereafter.
```

- [ ] **Step 3: Update acceptance criterion #4**

Replace:

```
   - A track-2 skill only when a technique appears in 2+ days
```

with:

```
   - A track-2 new-skill *proposal* (plus a `~skill proposed` CHANGELOG line
     and a `proposed` INDEX row) only when a technique appears in 2+ days
```

- [ ] **Step 4: Confirm internal consistency**

Re-read the Track 2 section and the architecture diagram block. Confirm the diagram's central-routine note ("writes `/memories/`, `/skills/`, `/proposals/`") is still accurate — it is, because accepted skills still land in `/skills/`. No diagram edit needed.

- [ ] **Step 5: Commit the spec changes and the feature design doc**

```bash
git add docs/specs/cognitive-consolidation-design.md docs/specs/2026-06-08-skill-proposals-design.md
git commit -m "docs(spec): Track 2 distills skills as proposals with CHANGELOG + INDEX record"
```

---

## Self-Review

**1. Spec coverage** (against `docs/specs/2026-06-08-skill-proposals-design.md`):
- Track 2 auto-apply → proposal queue → Task 3 (spec) + Task 2 (`/journal` accept installs). ✓
- Option-A encoding (`## New skill:` entry, 4-backtick fence, scope tag, filing rule) → described in Task 3 spec rewrite; consumed by Task 2 accept parsing. ✓
- `surface_proposals.py` broadened blurb + per-type labeling → Task 1. ✓
- `/journal` accept/skip/edit for new skills, propagate via journal `skills/` + sync → Task 2. ✓
- CHANGELOG ledger + INDEX manifest, hand-maintained, exact formats → Task 2 steps 2–4 + Task 3 spec. ✓
- Tests for new-skill surfacing/labeling → Task 1 steps 1–5. ✓
- Out of scope (private ROUTINE.md, per-user repo creation, Track 3) → untouched. ✓

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases"/"similar to". Every code/edit step shows literal content. ✓

**3. Type consistency:** `build_proposal_context`, `project_key_from_cwd`, `_iter_entries`, `_entry_label`, `_read_text`, `_first_nonempty` are defined in Task 1's full-module rewrite and referenced consistently. The `~/+/-skill <event> <scope>/<name>` CHANGELOG format and the `Skill | Scope | Status | Description | Provenance | Updated` table schema are identical in Task 2 (skill prose) and Task 3 (spec). The "new skill" label string emitted by `_entry_label` (Task 1) matches the assertions in Task 1's tests. ✓
