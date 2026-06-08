---
date: 2026-06-08
title: Skill proposals — distilled skills go through the proposal queue
status: approved
supersedes: Track 2 ("tier-2: auto-apply") in cognitive-consolidation-design.md
---

# Skill proposals — design spec

## Problem

The consolidator's **Track 2** currently auto-creates skills: when a technique
appears in 2+ sessions on different days, the nightly routine writes a
`SKILL.md` straight into `skills/global/` or `skills/projects/`, and every
device mirrors it silently on the next `SessionStart`. The user is never asked.

The user wants new skills **suggested**, not silently applied — routed through
the same `/journal accept|skip|edit` queue that already gates `feedback`
memories (Track 1b) and CLAUDE.md / existing-skill edits (Track 3).

## Decision

Track 2 changes from **auto-apply** to **proposal queue**. New skills are
written as proposal entries; nothing lands on a device until the user runs
`/journal accept`. The 2-sessions-on-different-days trigger threshold is
unchanged. Editing *existing* skills already went through Track 3 and stays
there — this change only affects **net-new** skill creation.

This is a behavior change to the published tooling. The canonical description
lives in this repo's design spec so every published user implements the same
behavior in their own per-user `~/claude-journal/consolidator/ROUTINE.md`. We
do not edit any user's private data repo.

## Proposal encoding (Option A)

A new skill is one `## `-delimited entry inside the existing per-project
proposal file `proposals/<date>-<project-key>.md`. No new filename pattern, so
`surface_proposals.py`'s project-scoped globbing is untouched.

Entry layout (literal text, with `FENCE4` standing for a line of exactly four
backticks — used so the inner block survives a `SKILL.md` body that contains
its own three-backtick code blocks):

    ## New skill: <skill-name>

    - **kind:** new-skill
    - **scope:** global            # or  project:<project-key>
    - **target:** skills/global/<skill-name>/SKILL.md
    - **provenance:** distilled from 2 sessions on 2026-06-05, 2026-06-07
    - **rationale:** <one paragraph citing the breadcrumbs that drove it>

    FENCE4 markdown
    ---
    name: <skill-name>
    description: <when-to-use description, description-gated>
    ---

    <full SKILL.md body — may itself contain ``` fenced code blocks>
    FENCE4

Key points:
- The inner `SKILL.md` is wrapped in a **4-backtick fence** so a skill body
  containing ordinary 3-backtick code blocks round-trips without ambiguity.
- `scope` (not the filename) decides where `accept` installs the skill.
- **Filing rule:** a global-scope skill is filed in the proposal file of the
  project whose breadcrumbs produced it (most recent originating project if it
  spans several), so it surfaces when the user next opens that project. The
  `scope: global` tag is what makes `accept` install it globally.

## Surfacing — `surface_proposals.py`

- Broaden the standing blurb from "behavioral rules or CLAUDE.md edits" to also
  name "new skills."
- Label each surfaced line by type, sniffed from the entry heading:
  `## New skill:` → "new skill"; feedback frontmatter → "feedback rule";
  a target file path / diff → "CLAUDE.md edit".
- Filtering logic (project-key match) is unchanged.

## `/journal` skill — accept / skip / edit for new-skill entries

Add a third proposal shape to `skills/journal/SKILL.md`:

- **accept:**
  1. Parse `scope`, `target`, and the 4-backtick-fenced `SKILL.md` body.
  2. Write the body to `~/claude-journal/<target>` (creating dirs).
  3. Mirror into this device's skills tree so no manual install is needed:
     global → `~/.claude/skills/<name>/`; project →
     `~/.claude/projects/<key>/.claude/skills/<name>/`. (Same destinations
     `sync_skills.py` uses; other devices pick it up via their next
     `SessionStart` sync — **accept once, available everywhere**.) Claude Code
     enumerates skills at session start, so an accepted skill is invocable from
     the next session — not necessarily mid-conversation in the running one.
  4. Update the data-repo record by hand (per the documented formats): append
     a `+skill accepted` line to `CHANGELOG.md` and flip the matching
     `skills/INDEX.md` row's Status from `proposed` to `accepted` (Updated =
     today).
  5. `git commit && git push` the journal repo so the skill + record propagate.
  6. Remove the accepted entry from the proposal file (delete the file if it
     was the only entry), commit + push.
  - **Collision:** if a skill with that name already exists, ask before
    overwriting — same guard the feedback-memory accept path uses.
- **skip:** append a `-skill skipped` line to `CHANGELOG.md`, remove the
  matching `skills/INDEX.md` row, then remove the new-skill entry from the
  proposal file (delete the file if it was the only entry). Commit + push.
- **edit:** open the proposal file in `$EDITOR`, then re-ask accept/skip.

## Demonstrating new skills in the data repo (ledger + manifest)

Every skill is recorded in the data repo two ways, so its lifecycle is plainly
visible without reading proposal internals:

**1. `CHANGELOG.md` — append-only event ledger.** One dated line per lifecycle
event:

```
2026-06-08 ~skill proposed global/condition-based-waiting — distilled from 2 sessions on 2026-06-05, 2026-06-07
2026-06-09 +skill accepted global/condition-based-waiting
2026-06-09 -skill skipped  project:-home-you-myproject/flaky-retry
```

`~` proposed, `+` accepted, `-` skipped. The consolidator writes the
`proposed` line; `/journal` writes `accepted` / `skipped`.

**2. `skills/INDEX.md` — current-state manifest.** An auto-maintained table
showing where each skill stands right now:

| Skill | Scope | Status | Description | Provenance | Updated |
|-------|-------|--------|-------------|------------|---------|
| condition-based-waiting | global | proposed | Wait on a condition, never a fixed sleep | 2 sessions: 2026-06-05, 2026-06-07 | 2026-06-08 |

Row lifecycle: consolidator inserts the row as `proposed`; `/journal accept`
flips it to `accepted`; `/journal skip` removes the row (the CHANGELOG retains
the skip event). The manifest therefore lists only proposed + accepted skills.

**Who maintains what.** The consolidator (per-user `ROUTINE.md`, normative per
the spec) writes the `proposed` CHANGELOG line and inserts the `proposed`
INDEX row at the same time it writes the proposal entry. The device-side
`/journal` skill updates both on accept/skip. **Both sides maintain these two
files by hand, following the exact formats above** — there is no shared Python
helper. The consolidator runs in the cloud against the *data* repo (without
this package), and a plugin SKILL.md cannot reliably invoke a bundled script:
`${CLAUDE_PLUGIN_ROOT}` is exported only to hook/MCP/LSP processes, not to
Bash the model runs during skill execution (confirmed against the Claude Code
plugins reference). Determinism comes from the format being simple and fully
specified, not from code. The formats are deliberately line-oriented (append a
line; upsert one table row) so a by-hand `Edit` is unambiguous.

## Changes by file

**This repo (published tooling):**

| File | Change |
|------|--------|
| `docs/specs/cognitive-consolidation-design.md` | Rewrite the Track 2 section (auto-apply → proposal queue); fold in the CHANGELOG + INDEX record; update the diagram note and acceptance criteria #3/#4. |
| `tools/journal/surface_proposals.py` | Broaden blurb; per-entry type labeling. Filtering unchanged. |
| `skills/journal/SKILL.md` | Add the new-skill accept/skip/edit branch; on accept/skip, hand-update `CHANGELOG.md` + `skills/INDEX.md` per the documented formats before the journal-repo commit/push. |
| `tests/journal/test_surface_proposals.py` | Add skill-proposal fixtures; assert a new-skill entry surfaces and is labeled "new skill," and that each entry in a mixed file is labeled by type. |

**Data repo (artifacts the published tooling maintains at runtime):**
`CHANGELOG.md` (ledger lines), `skills/INDEX.md` (manifest), and the
`skills/<scope>/<name>/SKILL.md` files themselves on accept.

## Out of scope

- Editing any user's private `~/claude-journal/consolidator/ROUTINE.md` (it's
  per-user; the spec is the normative source they follow).
- Per-user data-repo *creation* in `init` (init still clones a configured
  repo — a separate publication gap).
- Track 3 (existing-skill edits) — unchanged.

## Testing

- `surface_proposals`: a proposal file containing a `## New skill:` entry is
  surfaced with a "new skill" label; mixed files label each type; non-matching
  project keys still filter out.
- The `/journal` skill is prose, not unit-tested; its accept/skip/edit behavior
  is specified above and verified manually. Any pure helper extracted for
  parsing the fenced `SKILL.md` gets a unit test.

## Acceptance criteria

1. The consolidator (per the updated spec) emits net-new skills as
   `## New skill:` proposal entries, not silent `skills/` writes, and at the
   same time records a `~skill proposed` CHANGELOG line + a `proposed` INDEX
   row.
2. `surface_proposals.py` surfaces a skill proposal and labels it "new skill."
3. `/journal accept` on a skill proposal installs the `SKILL.md` into the
   journal repo's `skills/` tree, mirrors it locally, writes a
   `+skill accepted` CHANGELOG line, flips the INDEX row to `accepted`, pushes,
   and removes the entry. Other devices receive it via the existing
   `sync_skills` sync.
4. `/journal skip` writes a `-skill skipped` CHANGELOG line, removes the INDEX
   row, and removes the entry without installing; `/journal edit` opens it then
   re-asks.
5. The CHANGELOG line format (`~/+/-skill <event> <scope>/<name> — <prov>`) and
   the `skills/INDEX.md` table schema are specified exactly, so the
   consolidator and `/journal` produce identical formats by hand.
6. Existing proposal types (feedback, CLAUDE.md edit) and existing skill sync
   continue to work unchanged.
