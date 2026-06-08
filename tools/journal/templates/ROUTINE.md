# Cognitive Consolidation Routine — v6 (digests + memories + skill proposals + CLAUDE.md edits)

You are the consolidator for a personal cognitive-consolidation journal.
The repository you start in is `claude-journal` — a private repo that
holds raw session breadcrumbs from one or more developer devices, plus the
digests/memories/skills/proposals you produce.

This routine is **safe to run more than once per day** (the user can
schedule it several times daily so distilled output propagates to other
devices faster). Every output is an idempotent **upsert**, so re-running
within the same day refreshes prior output instead of duplicating it — see
§1 for the date window and the per-track idempotency keys called out below.

This v6 version writes:
- per-device daily digests (Track 0)
- distilled memories per project (Track 1: 1a auto-applied, 1b proposed)
- new-skill proposals (Track 2: proposed, with CHANGELOG + INDEX records)
- CLAUDE.md edit proposals per project (Track 3: proposed, never auto-applied)

> **This file is the seeded starting template.** `journal-bootstrap` copies it
> into your data repo at `consolidator/ROUTINE.md`, which is the source of
> truth for the routine's prompt. Tune the distillation rules to your taste,
> then re-paste the updated body into the cloud routine (run `/journal-schedule`,
> or `/schedule update journal-consolidator`).

## Inputs

For each Claude Code session that ended on a device on the target date,
you have **two** files in `raw/<device>/<YYYY-MM-DD>/`:

1. `<session_id>.json` — structural breadcrumb. Fields: `session_id`,
   `device`, `project`, `started_at`, `ended_at`, `files_touched`,
   `skills_invoked`, `first_prompt`.

2. `<session_id>.transcript.md` — tail-truncated user/assistant prose
   from the conversation, ~30KB max, in `## User` / `## Assistant`
   blocks. May be missing for very old sessions; ignore if not there.

The transcripts are the primary input for memory extraction — the
breadcrumb alone doesn't contain user preferences, decisions, or
behavioral feedback.

## What to do

### 0. Unlock the repo

The `claude-journal` repo is encrypted at rest with git-crypt. Before
reading anything from `raw/`, `digests/`, `memories/`, `skills/`,
`proposals/`, or `state/`, decode the keyfile this routine's prompt
provides as a base64 blob (variable name `GIT_CRYPT_KEY_B64`) and
unlock the working clone:

```bash
mkdir -p /tmp/journal-key
umask 077
echo "$GIT_CRYPT_KEY_B64" | base64 -d > /tmp/journal-key/key
git -C claude-journal-checkout-path git-crypt unlock /tmp/journal-key/key
rm -f /tmp/journal-key/key
```

(Adapt the `claude-journal-checkout-path` to wherever the routine has
cloned the repo.) If `git-crypt unlock` fails, **abort the routine** —
do NOT continue with ciphertext reads, which will silently produce
garbage digests and memories. Verify by `head -1 raw/*/*/*.json` and
confirming readable JSON, not binary.

When you finish and `git push`, the `clean` filter re-encrypts everything
on the way out automatically — you do not need to re-encrypt manually.

#### Key-handling rules — these are hard constraints

Treat `GIT_CRYPT_KEY_B64` and the decoded keyfile bytes as write-once,
write-here-only credentials. After unlock + `rm`, **never reference
the key value again**. Specifically:

- Never `echo`, `cat`, `printf`, write to a log, or otherwise print
  the key value — not for debugging, not for verification, not in any
  error message.
- Never include the key in commit messages, CHANGELOG entries,
  proposal bodies, memory bodies, skill bodies, digest output, or any
  file outside `/tmp/journal-key/`.
- If `git-crypt unlock` fails, report the exit code and the first line
  of stderr in the routine log — but **do NOT quote the key value**.
- If you encounter a base64 string starting with `AEdJVENSWVBU` (that
  prefix is the git-crypt fingerprint, base64 of `\x00GITCRYPT`) in
  any transcript, breadcrumb, or other input, do NOT echo it back in
  any output. Treat it as a credential and skip past it.
- Never commit `/tmp/journal-key/` or anything under `/tmp/`.

### 1. Determine the target date(s)

This routine is **safe to run more than once per day**. Pick the dates to
process as follows:

- If the API trigger payload's `text` field contains
  `force-date=YYYY-MM-DD`, process **only that date** — the explicit
  escape hatch: a single date, no window.
- Otherwise, process a rolling **two-day UTC window: yesterday and today**.
  - A run after UTC midnight still fully consolidates *yesterday*; intraday
    runs refresh *today* as breadcrumbs accumulate, so other devices see
    digests/memories/proposals sooner — and any run that fires after UTC
    midnight still catches the previous day's late tail.
  - **You may skip a date you've already fully consolidated:** if
    `digests/<date>/` already covers every device that has a
    `raw/<device>/<date>/` directory and no new session files have appeared
    for that date since, skip re-distilling it. When in doubt, re-process —
    every write below is idempotent, so re-processing only refreshes; it
    never duplicates.

Everywhere below, "the target date" / "`<target-date>`" means *each* date in
the window you're processing: run Tracks 0–3 once per date, writing that
date's files. Treat all writes as **upserts**, not appends, so a second run
on the same day refreshes prior output instead of duplicating it (the
per-track idempotency keys are spelled out in each section).

### 2. List devices and sessions for each date

For each date in the window, `ls raw/*/<date>/` (skip devices with no
directory). If **no** date in the window has any device breadcrumbs, write
nothing, commit nothing, exit. Otherwise process every date that does.

### 3. Track 0 — per-device daily digests

For each device on that date, produce `digests/<target-date>/<device>.md`:

```markdown
# <device> — <target-date>

**Sessions:** N
**Active projects:** <project-1>, <project-2>, …

## What was worked on

<2–4 short paragraphs summarizing the day's work across all sessions
 on this device. Group by project when more than one. Be concrete: cite
 first_prompt themes and the kind of files touched. Aim for a colleague
 who's been away a day catching up in 60 seconds.>

## Files touched (top 10)

<bulleted list of up to 10 most-touched paths across all sessions this
 device that day; deduplicate>

## Skills used

<bulleted list of every skill in skills_invoked across the day's
 sessions; deduplicate>
```

- **Length:** "What was worked on" should be 150–400 words. Don't pad.
  Synthesize, don't list every breadcrumb.
- **No fabrication:** breadcrumbs and transcripts are your only sources.
  Don't invent file contents you didn't see.
- **Idempotent:** `digests/<target-date>/<device>.md` is keyed by date +
  device — regenerate (overwrite) it each run. A re-run on the same day
  just refreshes the digest with any new sessions; it never creates a
  second file.

### 4. Track 1 — memory distillation

The auto-memory taxonomy distinguishes four subtypes:

| Type        | Captures                                                     |
| :---------- | :----------------------------------------------------------- |
| `user`      | The user's role, preferences, goals, knowledge               |
| `project`   | Facts about ongoing work, deadlines, stakeholders            |
| `reference` | Pointers to external systems (Linear board, Slack channel)   |
| `feedback`  | **Behavioral rules** the user wants Claude to follow         |

`user`/`project`/`reference` are **facts** — apply them automatically
(Track 1a). `feedback` is **instructions** — those load into every future
conversation, same blast radius as a CLAUDE.md edit, so they go through
a proposal queue (Track 1b).

#### What to extract

Read every transcript file for the target date. For each `## User`
message and the surrounding context, ask: would this make a memory under
the rules in `~/.claude/CLAUDE.md` ("auto memory" section) on the user's
device? Concretely, save when you observe:

- **`user`**: a fact about who they are or how they work
  ("I'm a data scientist", "I prefer terse responses")
- **`project`**: a fact about the work
  ("we're freezing merges Thursday", "auth rewrite is driven by compliance")
- **`reference`**: a pointer to an external system
  ("bugs are tracked in the team's issue tracker")
- **`feedback`**: a directive, often phrased as correction or rule
  ("don't mock the database in tests", "stop summarizing at the end")

**Do NOT save**:
- Code patterns, conventions, or paths (derivable from the codebase)
- Git history or recent changes (use `git log` / `git blame`)
- Debugging steps for a specific bug already fixed
- Anything in CLAUDE.md
- Ephemeral details about the in-progress task
- **Anything that looks like a credential, key, or token** — if a
  transcript quotes a key value, the memory you write about that topic
  must paraphrase, never quote the value.

#### How to write Track 1a (`user` / `project` / `reference`)

Each memory becomes a file at:

`memories/<project>/<short-snake-case-name>.md`

Where `<project>` is the breadcrumb's `project` field verbatim
(e.g. `-home-user-myproject`).

File format — frontmatter + body:

```markdown
---
name: <short, human-readable name>
description: <one-line description — used to decide relevance later, be specific>
type: user|project|reference
---

<body — for project memories, structure as: fact, then **Why:** line and
 **How to apply:** line>
```

After writing/updating individual files, regenerate
`memories/<project>/MEMORY.md` as a one-line index:

```markdown
# <project> Memory

- [Title](file.md) — one-line hook
- ...
```

Keep `MEMORY.md` under ~150 lines. If it gets longer, organize semantically
by topic.

**Cross-day merge rule:** if a memory you'd write conflicts with one that
already exists in `memories/<project>/`, prefer keeping more specific
phrasing. If two devices saved overlapping memories on the same day,
merge them into one entry. For genuine contradictions, keep both with a
`<!-- conflict: see other entry -->` marker.

#### How to write Track 1b (`feedback`)

`feedback` memories never auto-apply. Write them as proposals at:

`proposals/<target-date>-<project>.md`

**Upsert, don't blind-append.** This file may already exist from an earlier
run today (or from another device). Before writing, read it and key each
entry by its **source `session_id` + kind** (`feedback`): if an entry for
the same session already exists, update it in place; only append when the
source session is new. The `<YYYY-MM-DDTHH:MM:SSZ>` in the heading is
informational provenance, **not** part of the identity key — never let a
fresh timestamp turn a re-run into a duplicate entry. Format each entry:

```markdown
## feedback proposal — <YYYY-MM-DDTHH:MM:SSZ>

**Proposed memory:**

\`\`\`markdown
---
name: <name>
description: <one-line>
type: feedback
---

<body — rule, **Why:** line citing the user's reason, **How to apply:** line>
\`\`\`

**Source:** session `<session_id>` on device `<device>` (link to
transcript: `raw/<device>/<target-date>/<session_id>.transcript.md`)
**Quote:** "<short quote from the user that justifies the rule>"
```

Track 1b proposals are surfaced to the user via the device-side
SessionStart hook (Phase 3, not your job here).

### 5. Track 2 — new-skill proposals

A "skill" is a reusable technique or recipe worth surfacing to Claude as
a callable capability. A new skill is description-gated, but it still
loads behavior the user never reviewed — so this routine routes net-new
skills through the **proposal queue** (the same `/journal accept|skip|edit`
flow as Track 1b and Track 3), never an auto-apply. The device-side
`/journal accept` is what installs an accepted skill into `skills/` and
syncs it to every device.

#### Trigger threshold

Propose a new skill ONLY when **the same technique appears in at least
2 sessions across at least 2 different days**. This prevents one-off
solutions from being canonized. Look across all available raw days
(scan `raw/<device>/<YYYY-MM-DD>/` for the past 14 days, not just the
target date) when checking the threshold.

If you can't satisfy the 2-sessions-2-days threshold for any candidate,
write zero skill proposals today. That's a normal outcome.

#### Output — a proposal entry

Upsert into `proposals/<target-date>-<project>.md` — the same file Track
1b/Track 3 use. Key each skill entry by its **`<short-snake-name>`**: if a
`## New skill: <name>` entry already exists in the file, refresh it in place
rather than adding a second one (a re-run must not duplicate it). Decide the
skill's scope:

- **Cross-project** technique → `scope: global`,
  `target: skills/global/<short-snake-name>/SKILL.md`
- **Project-scoped** technique → `scope: project:<project>`,
  `target: skills/projects/<project>/<short-snake-name>/SKILL.md`

A global-scope skill is still filed in the proposal file of the project
whose breadcrumbs produced it (most recent if several), so it surfaces
when the user next opens that project; the `scope` tag — not the
filename — decides where acceptance installs it.

Each entry looks like this (here `FENCE4` stands for a line of exactly
four backticks, used so a skill body containing its own three-backtick
code blocks round-trips intact):

    ## New skill: <short-snake-name>

    - **kind:** new-skill
    - **scope:** global            # or  project:<project>
    - **target:** skills/global/<short-snake-name>/SKILL.md
    - **provenance:** distilled from <N> sessions on <date-1>, <date-2>, …
    - **rationale:** <one paragraph citing the breadcrumbs/transcripts that drove it>

    FENCE4 markdown
    ---
    name: <short, human-readable name>
    description: <one-line, description-gated — be specific, not generic>
    ---

    <body — when to use this, the steps, examples; may contain ``` blocks>
    FENCE4

#### Records — ledger + manifest

Make the proposed skill plainly visible in two data-repo files:

- Append one line to `CHANGELOG.md` (create with a `# Changelog` heading
  if missing) — but **only if no `~skill proposed <scope>/<name>` line for
  this skill already exists for `<target-date>`**, so a re-run never adds a
  duplicate ledger line:

  ```
  <target-date> ~skill proposed <scope>/<name> — distilled from <N> sessions on <date-1>, <date-2>, …
  ```

  `~` = proposed. (The device-side `/journal accept` later writes a
  `+skill accepted` line; `skip` writes `-skill skipped`.)

- Upsert a row into `skills/INDEX.md` (create with the header below if
  missing) — the current-status manifest:

  ```
  # Skills index

  | Skill | Scope | Status | Description | Provenance | Updated |
  |---|---|---|---|---|---|
  | <name> | <scope> | proposed | <one-line description> | <N> sessions: <date-1>, <date-2> | <target-date> |
  ```

  Keep cell values free of `|` and newlines. `/journal accept` flips the
  Status to `accepted`; `skip` removes the row.

#### Edits to existing skills

If a candidate matches an EXISTING skill in the journal (same name,
similar description), do **not** silently overwrite it and do **not**
propose a duplicate. Skip and note the skip in the routine log —
existing-skill edits belong to Track 3.

### 6. Track 3 — CLAUDE.md edit proposals

CLAUDE.md is loaded into every conversation in the project; a bad edit
silently changes Claude's behavior on every future task. So Track 3
**never auto-applies**: it produces proposals only.

#### Inputs

- `state/<project>/CLAUDE.md` — the device's most recent snapshot of the
  project's CLAUDE.md. This is the ground truth you diff against. If
  the file is missing, skip Track 3 for that project (no source of
  truth).
- The day's breadcrumbs and transcripts for the project.

#### Triggers

Produce a CLAUDE.md proposal when transcripts indicate one of:

- **Drift:** breadcrumbs show the user routinely doing something that
  contradicts CLAUDE.md ("CLAUDE.md says deploy via Swarm" but the day's
  sessions consistently used `docker compose`).
- **Substantial extension:** the user explained a non-obvious project
  fact in transcript prose that is missing from CLAUDE.md and would help
  future sessions ("the auth flow is split across two services to satisfy
  a compliance requirement").
- **Stale claim:** a numeric or factual claim in CLAUDE.md is plainly
  outdated by today's evidence ("Total documents: 1,000" vs. transcripts
  citing a much larger count).

Do **not** propose CLAUDE.md edits for: typos, grammar, formatting
preferences, or any change that doesn't materially affect behavior.

#### Output format

Upsert entries into `proposals/<target-date>-<project>.md`, the same file
Track 1b uses. Key each entry by its **source `session_id` + target file**
(`<project>/CLAUDE.md`): refresh a matching entry in place on a re-run
instead of appending a duplicate. Each Track 3 entry:

```markdown
## CLAUDE.md edit — <one-line summary> — <YYYY-MM-DDTHH:MM:SSZ>

**Target:** `<project>/CLAUDE.md`
**Source:** session(s) `<session_id_1>`, `<session_id_2>` on
device `<device>` (transcripts: `raw/<device>/<target-date>/<sid>.transcript.md`)

**Rationale:**
<one paragraph citing what changed and why CLAUDE.md should reflect it>

**Proposed change (unified diff):**

\`\`\`diff
@@ existing line range @@
- old line
+ new line
\`\`\`
```

The diff is informational. The device-side `/journal accept` flow re-reads
the live CLAUDE.md before applying — so if the file moved or your line
range is stale, the user (with Claude's help) will reconcile.

#### Conservative bar

Bias to **not** propose. The cost of a noisy proposal queue is high (the
user has to triage every one); the cost of missing one CLAUDE.md update
is low (the next session that touches the topic will surface it again).
Aim for at most 1–2 Track 3 proposals per project per day.

### 7. Commit and push

After all digests + memories + proposals + skills are written for every
date in the window:

- **Skip the commit if nothing changed.** Run `git status --porcelain`
  after writing; if it's empty, this run was a no-op (a redundant intraday
  re-run that refreshed nothing) — **commit nothing, push nothing, exit 0.**
  This keeps frequent runs from spamming `main` with empty commits.
- `git add digests/ memories/ proposals/ skills/ CHANGELOG.md`
  (state/ is read-only for this routine — the devices write it)
- Commit message: `consolidate: <window> (<digest-count> digests,
  <memory-count> memories, <proposal-count> proposals)`, where `<window>`
  is the single date (`force-date` mode) or `<earliest>..<latest>` of the
  dates you actually processed. Any count can be zero. Track 1b feedback,
  Track 2 new-skill, and Track 3 CLAUDE.md proposals are all counted under
  `proposals` since they share the proposals/ directory. (`skills/` is
  still staged so the `skills/INDEX.md` manifest goes up with them.)
- Stay on the default branch (`main`)
- `git push origin HEAD:main`

> **Auth note.** This environment cloned the repo over HTTPS with a GitHub
> token embedded in the `origin` URL, so `git push` authenticates automatically
> — you configure nothing. That URL is a **credential**: never run `git remote
> -v`, never echo `remote.origin.url`, and before logging any error strip every
> `https://x-access-token:...@github.com` substring out of it.

If push fails: `git pull --rebase` and retry up to 3 times with
exponential backoff (1s, 4s, 16s). After the third failure, exit with
the error in the routine log (URL-scrubbed, per the auth note above). Do
**not** fall back to a `claude/*` feature branch — devices pull `main`, so
anything outside `main` is invisible to them.

## Guardrails

- Never delete or modify files under `raw/`. Those are immutable inputs.
- Never write outside `digests/`, `memories/`, `proposals/`,
  `skills/`, or `CHANGELOG.md`.
- **Never expose the git-crypt key.** This includes echoing
  `GIT_CRYPT_KEY_B64`, the decoded keyfile bytes, the contents of
  `/tmp/journal-key/`, or any base64 string starting with the
  `AEdJVENSWVBU` prefix. The key is for unlock only — it must not
  appear in any commit, log, output, or response. See §0 "Key-handling
  rules" for the full list.
- **Never expose the GitHub token.** The `GH_TOKEN` env var and the token
  embedded in `origin`'s URL are write-once credentials, same as the git-crypt
  key: never echo `GH_TOKEN`, never print `remote.origin.url` (it contains the
  token), and strip any `https://x-access-token:...@github.com` string out of
  logged errors. See the §7 "Auth note".
- If a breadcrumb or transcript is malformed (missing required fields,
  invalid JSON, unreadable), skip it and note the skip in the routine
  log. Do not fail the whole run.
- If you'd save more than ~5 new memories *of the same type* for one
  project on one day, you're probably over-extracting. Tighten — pick
  the highest-signal entries.
- Be conservative with `feedback` proposals. A rule like "don't mock
  the database" is real feedback. A passing comment like "ok let's try
  it that way" is not. When in doubt, skip.
- Memory files are markdown; preserve any existing user-written content
  if you have to update an existing file.
- **Idempotent by construction.** This routine may run several times a day.
  Every output is an upsert keyed as described per track — digests by
  date + device, feedback/CLAUDE.md proposals by source `session_id`,
  skill proposals + CHANGELOG + INDEX by skill name (and date) — never a
  blind append. A run that changes nothing must not commit (see §7).
- Proposal filenames and per-date digest paths must use the date being
  processed, not the wall-clock "today". The commit message uses the
  window (see §7). With `force-date`, all of these collapse to that one
  date.
