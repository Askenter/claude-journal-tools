---
date: 2026-04-28
title: Cognitive consolidation pipeline — design spec
status: approved
---

# Cognitive consolidation pipeline — design spec

## Purpose

Build a system that mirrors human memory consolidation during sleep: each day,
across multiple devices, conversations with Claude generate experience; each
night, a scheduled routine distills that experience into long-term knowledge
that persists across sessions, devices, and projects.

The goal is "the Claude on my laptop tomorrow knows what the Claude on my
desktop figured out today, without me copy-pasting anything."

## Non-goals

- Not a conversation history viewer or search tool.
- Not a generic backup system — only distilled artifacts persist long-term;
  raw transcripts are out of scope (only lightweight breadcrumbs are synced).
- Not multi-user. Single-user system, all devices belong to one person.
- Not a release/code review pipeline. Project source code stays in project
  repos; this system manages knowledge artifacts, not application code.

## High-level architecture

Two-tier system:

```
┌─────────── DEVICE A ──────────┐    ┌─────────── DEVICE B ──────────┐
│ Stop hook → synthesize        │    │ Stop hook → synthesize        │
│   breadcrumb (Haiku, ~1s)     │    │   breadcrumb (Haiku, ~1s)     │
│   then push on session end    │    │   then push on session end    │
│                               │    │                               │
│ SessionStart hook → pull,     │    │ SessionStart hook → pull,     │
│   apply low-risk memories +   │    │   apply low-risk memories +   │
│   skills, surface proposals   │    │   skills, surface proposals   │
│   (feedback + CLAUDE.md)      │    │   (feedback + CLAUDE.md)      │
└──────────────┬────────────────┘    └────────────┬──────────────────┘
               │ git push/pull                    │ git push/pull
               ▼                                  ▼
        ┌─────────────────────────────────────────────┐
        │   GitHub: askenter/claude-journal (private) │
        │                                             │
        │   /raw/<device>/<date>/*.json               │
        │   /digests/<date>/<device>.md               │
        │   /memories/<project>/...                   │
        │   /skills/global/<name>/SKILL.md            │
        │   /skills/projects/<project>/<name>/...     │
        │   /proposals/<date>-<project>.md            │
        │   /CHANGELOG.md                             │
        │   /consolidator/ROUTINE.md                  │
        └──────────────┬──────────────────────────────┘
                       │
                       ▼
        ┌─────────────────────────────────────────────┐
        │   Claude Routine (scheduled remote agent)    │
        │   03:00 UTC nightly + /consolidate-now      │
        │                                             │
        │   reads /raw/*/yesterday/*                   │
        │   distills three tracks                     │
        │   writes /memories/, /skills/, /proposals/  │
        │   appends to /CHANGELOG.md                  │
        │   commits + pushes                          │
        └─────────────────────────────────────────────┘
```

**Why this shape works:**
- Devices never need to be powered on at any specific time. The Stop hook
  pushes breadcrumbs on every session exit; the routine runs in the cloud.
- LLM work is split asymmetrically: a small per-session Haiku call produces
  *interpreted* breadcrumbs (summary, decisions, facts learned), and the
  heavy cross-device synthesis runs once per night in the central routine.
  The routine gets meaning-bearing input instead of having to reverse-engineer
  intent from raw tool-use logs.
- One canonical git repo as the source of truth for distilled knowledge.
- Eventual consistency: offline devices catch up on next online session.

## Components

### 1. The `claude-journal` private GitHub repo

Acts as the hippocampus — the central store for breadcrumbs, distilled
artifacts, and the consolidator routine itself.

Layout:

```
claude-journal/
├── raw/
│   └── <device>/<YYYY-MM-DD>/<session-id>.json
├── digests/
│   └── <YYYY-MM-DD>/<device>.md
├── memories/
│   └── <project-key>/
│       ├── MEMORY.md
│       └── *.md
├── skills/
│   ├── global/<skill-name>/SKILL.md
│   └── projects/<project-key>/<skill-name>/SKILL.md
├── proposals/
│   └── <YYYY-MM-DD>-<project-key>.md
├── CHANGELOG.md
└── consolidator/
    ├── ROUTINE.md
    └── prompts/
```

`<project-key>` is the slugified absolute project path (e.g.,
`-home-you-myproject`), matching the auto-memory directory naming convention in
`~/.claude/projects/`.

`<device>` is a stable name registered at first-time setup (e.g., `laptop`,
`workstation`).

**Repo settings required for the routine to write to `main`:**
- Private visibility (sensitive data flows through it).
- **Allow unrestricted branch pushes** enabled for the routine on this
  repo. By default, Claude routines can only push to `claude/`-prefixed
  branches; `claude-journal` is the dedicated knowledge repo, so unlocking
  pushes to `main` is appropriate. Configure under the routine's
  **Permissions** tab.

### 2. Per-device Stop hook

Path: `~/.claude/hooks/journal-on-stop.sh`. Triggered by Claude Code on every
session exit.

Behavior:

1. Read the session's tool-use history. Extract structural breadcrumb fields:
   - session ID, start/end timestamps
   - project key (derived from CWD)
   - files touched via `Edit`, `Write`, or `NotebookEdit` (paths only)
   - skills invoked during the session (names only)
   - first user prompt (truncated to ~200 chars)
2. Run a one-shot Haiku call (~1s, single request) over the session's
   tool-use history to synthesize four additional fields:
   - `session_summary` — one-sentence description of what happened
   - `decisions` — list of one-line decisions made during the session
   - `facts_learned` — list of one-line non-obvious findings
   - `open_questions` — list of unresolved questions or follow-ups

   On LLM failure (offline, API down, timeout, parse error): omit these
   four fields and continue. The structural breadcrumb alone is still a
   valid input for the central routine.
3. Combine structural + synthesized fields into one breadcrumb JSON.
   Append to `~/.claude/journal-buffer.jsonl`.
4. `cd ~/claude-journal && git pull --rebase --quiet`.
5. Move buffered breadcrumbs into `raw/<device>/<date>/<session-id>.json`,
   one file per session.
6. `git add raw/ && git commit -m "raw: <device> <date>" && git push`.
7. On any failure in steps 4–6 (offline, push rejected, etc.): leave the
   buffer intact; exit cleanly. Next successful run drains the backlog.

The Haiku call (step 2) is the only slow step (~1s), and it degrades
gracefully on failure — never blocks the user, never loses the breadcrumb.

### Breadcrumb schema

A breadcrumb under `raw/<device>/<date>/<session-id>.json` looks like:

```json
{
  "session_id": "0a7e6abf-4198-4441-ab11-9e95d603dc63",
  "device": "laptop",
  "project": "-home-you-myproject",
  "started_at": "2026-04-28T09:14:32Z",
  "ended_at":   "2026-04-28T10:02:18Z",
  "files_touched": [
    "src/api.py",
    "frontend/components/ChatInput.tsx"
  ],
  "skills_invoked": ["superpowers:brainstorming"],
  "first_prompt": "Help me design a memory consolidation pipeline...",

  "session_summary": "Designed a multi-device memory consolidation pipeline with tiered auto-apply.",
  "decisions": [
    "Use a private claude-journal repo as the central store",
    "Tier-3 CLAUDE.md edits go through inline confirm, not auto-apply"
  ],
  "facts_learned": [
    "Claude routines run on Anthropic infrastructure, not the local box"
  ],
  "open_questions": [
    "Where should /journal accept|skip|edit live: project-local or global?"
  ]
}
```

The four `session_summary` / `decisions` / `facts_learned` / `open_questions`
keys are present when the Haiku call succeeded, and absent when it didn't.
The central routine handles either case.

### 3. Per-device SessionStart hook

Path: `~/.claude/hooks/journal-on-start.sh`. Triggered at the start of every
Claude Code session.

Behavior:

1. `cd ~/claude-journal && git pull --rebase --quiet` (best-effort; skip on
   failure).
2. Sync `memories/<current-project>/` → `~/.claude/projects/<key>/memory/`,
   but only for low-risk subtypes (`user`, `project`, `reference`). These
   apply silently. `feedback`-type memories are NOT synced here — they are
   handled via the proposal queue in step 4.
3. Sync `skills/global/` → `~/.claude/skills/` and
   `skills/projects/<current-project>/` → `<project>/.claude/skills/`. These
   are *accepted* skills (already promoted into the `skills/` tree via
   `/journal accept`), so they apply silently. New-skill *proposals* are not
   synced here — they are surfaced in step 4.
4. Check `proposals/` for unprocessed entries scoped to the current project.
   Three kinds may be present:
   - new-skill proposals (track-2)
   - CLAUDE.md / existing-skill edit proposals (track-3)
   - `feedback`-memory proposals (track-1b)

   If any exist, emit a `SessionStart` system-reminder block summarizing
   them and instructing the assistant to surface them inline at the start of
   the first response. The user resolves each via
   `/journal accept|skip|edit`.
5. **Morning digest:** if any low-risk memories or new skills were synced
   in steps 2–3 since the last time this device ran the hook, emit a
   one-line summary as a system-reminder for visibility:

   ```
   📓 applied since last session: 2 memories (project, user), 1 new skill (global/condition-based-waiting). `/journal undo <id>` to revert any.
   ```

   The hook tracks "last seen commit on `claude-journal`" in
   `~/.claude/journal-last-seen` to compute the diff. Visibility without a
   review gate.

### 4. Central routine (scheduled remote agent)

Implemented as a Claude Code routine
([docs](https://code.claude.com/docs/en/routines)) — a saved cloud session
with a prompt, repository, environment, and triggers. Created from the CLI
with `/schedule` or from `claude.ai/code/routines`.

**Config:**
- **Repository:** `claude-journal` (cloned on every run from the default
  branch). Enable **Allow unrestricted branch pushes** on this repo so the
  routine commits straight to `main`; otherwise pushes are restricted to
  `claude/`-prefixed branches and devices wouldn't see them via `git pull`.
- **Environment:** default cloud environment is sufficient. Network access
  enabled (for git push and any MCP calls).
- **Connectors:** none required for v1. The routine reads/writes only the
  cloned repo.
- **Model:** picked at routine creation in the prompt form.

**Triggers (combined on the same routine):**
- **Schedule trigger:** custom cron `0 3 * * *` (03:00 UTC nightly). Set via
  `/schedule update` after creation; the form's preset frequencies don't
  include arbitrary cron expressions. Minimum interval is 1 hour.
- **API trigger:** generates a `/fire` HTTP endpoint plus a bearer token.
  The user-facing `/consolidate-now` slash command POSTs to this endpoint
  to force an out-of-cycle run. The optional `text` field can carry
  `force-date=YYYY-MM-DD` to consolidate a specific date.

**Prompt source of truth:** the prompt body lives in
`claude-journal/consolidator/ROUTINE.md` (version-controlled, reviewable in
git). The routine config on `claude.ai/code/routines` holds a copy that
must be kept in sync — when the file changes, edit the routine and paste
the updated body into the prompt field. The `ROUTINE.md` file is canonical;
the cloud config is a mirror.

On each run:

1. Clone or pull `claude-journal`.
2. List all `raw/*/<yesterday>/*.json`. If empty, exit.
3. For each device, generate `digests/<yesterday>/<device>.md` — a one-page
   markdown summary of what that device worked on yesterday.
4. Run the three-track distillation (see below). Write outputs to
   `memories/`, `skills/`, `proposals/`.
5. Append a one-line entry to `CHANGELOG.md` for every track-2 (skill) or
   track-3 (proposal) artifact.
6. `git commit && git push`.
7. On failure: retry up to 3 times with exponential backoff. After the third
   failure, open a GitHub issue on `claude-journal` with the error details.
   Yesterday's raw breadcrumbs are preserved, so the next night's run will
   include them.

## The three distillation tracks

Each track has different "what to keep" rules and different auto-apply
policies.

### Track 1 — Memories (split into 1a auto-apply / 1b proposal queue)

The auto-memory taxonomy distinguishes four subtypes: `user`, `project`,
`reference`, and `feedback`. Three of these are *facts* (low risk: a wrong
fact gets caught when Claude says something obviously off). The fourth,
`feedback`, encodes *instructions* — rules that directly shape Claude's
behavior on every future task. A bad `feedback` entry has the same blast
radius as a bad CLAUDE.md edit.

So Track 1 splits into two policies based on subtype:

#### Track 1a — `user` / `project` / `reference` memories (auto-apply + morning digest)

**Source rules:** existing auto-memory taxonomy. Same exclusions as today
(no code patterns, no git history, no debugging recipes, no ephemeral
state).

**Output:** writes/updates files in `claude-journal/memories/<project>/`
(including `MEMORY.md` index). On next `SessionStart`, the hook copies
non-`feedback` files to `~/.claude/projects/<project>/memory/` on each
device.

**Cross-device merge rule:** if two devices produced overlapping memories on
the same day, the routine LLM merges them into a single entry, keeping the
more specific phrasing. Genuine contradictions are kept as both entries with
a `<!-- conflict: see other entry -->` marker for manual review.

**Visibility:** SessionStart hook lists newly-applied memories in the
morning digest (see hook step 5). No review gate, but you see what was
added.

**Auto-apply rationale:** these are facts, not instructions. Wrong facts
self-correct (Claude says something off, you notice, you delete the entry).
Volume is too high for a per-entry review without fatigue.

#### Track 1b — `feedback` memories (proposal queue)

**Source rules:** same auto-memory rules for `feedback` type. Trigger: a
`feedback` memory describes a behavioral rule the user wants Claude to
follow (e.g., "never mock the database in tests"; "always run tests after
index rebuilds").

**Output:** routine writes the proposed feedback memory as a proposal file
under `proposals/<date>-<project>.md` (same directory as track-3
proposals). The proposal includes the proposed entry text and a rationale
citing which breadcrumbs drove it.

**Surfacing:** SessionStart hook surfaces the proposal inline alongside any
track-3 proposals — same `/journal accept|skip|edit` flow.

**Auto-apply rationale (or rather, why we don't):** `feedback` entries are
behavioral rules. They load into every conversation and silently change how
Claude responds. Same risk profile as CLAUDE.md, same treatment.

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

### Track 3 — CLAUDE.md edits + edits to existing skills (tier-3: proposal queue)

**Trigger:** the routine detects that breadcrumbs contradict, or
substantially extend, an existing CLAUDE.md or skill — e.g., "the project
deploys via Docker Compose now, but CLAUDE.md still says Swarm".

**Output:** routine writes a proposal file to
`proposals/<date>-<project>.md` containing:
- The target file path (e.g., `myproject/CLAUDE.md`)
- The proposed diff in unified-diff format
- A one-paragraph rationale citing which breadcrumbs drove the change

**Surfacing:** on next `SessionStart` in the affected project, hook injects
a system-reminder block:

```
📓 claude-journal has 1 proposal from 2026-04-28:
  myproject/CLAUDE.md (lines 47-52): replace "Swarm" with "Docker Compose"
  Rationale: 4 sessions this week deployed via compose; deploy.sh has no
    swarm commands.
  Reply "/journal accept", "/journal skip", or "/journal edit"
```

**User actions:**
- `/journal accept` → assistant applies the diff to the project file,
  `git commit` to the project repo locally (push is the user's call),
  removes the proposal from the queue.
- `/journal skip` → deletes the proposal. No further surfacing.
- `/journal edit` → opens the proposal for the user to modify before
  accepting.

**Auto-apply rationale (or rather, why we don't):** CLAUDE.md is loaded into
every conversation in the project. A bad edit silently changes Claude's
behavior for every future task. A 5-second confirm is cheap insurance.

## Edge cases and failure modes

| Case | Behavior |
|------|----------|
| Device offline at session end | Buffer stays local; next online session flushes the backlog. |
| Push conflict on `claude-journal` | Stop hook does `git pull --rebase` then retries push. On unresolvable conflict, leave the breadcrumb in the local buffer; next run handles it. |
| Routine fails (network, LLM, etc.) | Up to 3 retries with backoff. After third failure, open a GitHub issue. Raw breadcrumbs are preserved; next night includes them. |
| Two devices produced contradictory memories same day | LLM merges. Irreconcilable contradictions kept as separate entries with conflict marker. |
| Accept a proposal but the target file changed since proposal was written | Apply fails cleanly; routine re-generates the proposal against the current file on the next nightly run. |
| Project rename / `<project-key>` changes | v1: out of scope. Manual remap. |
| Sensitive content in breadcrumb (API key in a prompt) | v1: not solved. Repo is private. v2 may add a redaction pass in the Stop hook. |
| `claude-journal` repo doesn't exist yet | Setup script creates it via `gh` CLI; idempotent. |
| First-time setup on a new device | `claude-journal init <device-name>` script: clones repo, registers device, installs hooks. |
| Stop hook itself fails | Hook exits with code 0 (never block the user). Failure is logged to `~/.claude/journal-buffer.log`. |
| Haiku call in Stop hook fails (offline, API error, timeout, malformed output) | Omit the four synthesized fields. Structural breadcrumb is still written and pushed. Central routine consumes either schema. |

## Acceptance criteria

The system is considered correctly implemented when:

1. The `claude-journal` repo exists and is private on the user's GitHub
   account, with the layout above.
2. The Stop hook pushes a valid breadcrumb to `raw/<device>/<date>/` after
   every session exit on any registered device.
3. The SessionStart hook applies track-1a memories (`user`, `project`,
   `reference`) silently, surfaces track-1b (`feedback`-memory), track-2
   (new-skill), and track-3 (CLAUDE.md / existing-skill) proposals as inline
   system-reminders tagged by type, and emits the morning digest line when
   applicable. Newly *accepted* skills sync silently thereafter.
4. The central routine, when run manually with at least one day of seeded
   breadcrumbs across two devices, produces:
   - A digest per device under `digests/<date>/`
   - At least one track-1a memory if facts are present
   - At least one track-1b proposal if a behavioral rule was learned
   - A track-2 new-skill *proposal* (plus a `~skill proposed` CHANGELOG line
     and a `proposed` INDEX row) only when a technique appears in 2+ days
   - A track-3 proposal when CLAUDE.md drift is detected
5. `/journal accept`, `/journal skip`, `/journal edit` work end-to-end on
   both track-1b and track-3 proposals.
6. `/consolidate-now` triggers the routine out of cycle and produces the
   same outputs as a scheduled run.
7. Offline session-end produces no errors; backlog flushes on next online
   session.
8. The routine's prompt body in `claude.ai/code/routines` matches the
   contents of `claude-journal/consolidator/ROUTINE.md` byte-for-byte at
   the time of last edit. Drift between the two is treated as a config
   bug, not a feature.
9. The routine has both a schedule trigger (`0 3 * * *` UTC) and an API
   trigger configured. POSTing to the API endpoint with a valid bearer
   token starts a new run within seconds and produces outputs equivalent
   to a scheduled run.

## Open questions for v2 (out of scope for v1)

- Per-device redaction of sensitive content before push.
- Web UI for browsing the journal repo (currently you read it via GitHub or
  `git log`).
- Automated project-key remap when a project moves on disk.
- Routine cost monitoring and budget cap.
- Multi-user / shared-repo mode (e.g., a team brain).
