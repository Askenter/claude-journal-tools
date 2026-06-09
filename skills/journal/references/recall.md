# `/journal recall` — answer from the consolidated journal

> Reference for the `journal` skill's `recall` action. The user reached here by
> running `/journal recall <question>` (e.g. `what did I do yesterday`, `what do
> I know about the auth rewrite`), or by asking what they did on some day / what
> the journal knows about a topic. Follow it exactly.

You answer **from the journal's distilled outputs**, not by reconstructing
work from raw transcripts or git. The mechanical part (pull, unlock check,
which digests exist, gap detection, memory listing) is done by
`tools/journal/recall.py`. Resolving the question's time phrase and synthesizing
the answer are yours.

The tools checkout (the directory holding `scripts/` and `tools/`) is `$TOOLS`
below — substitute its real absolute path. The data repo path honors
`$CLAUDE_JOURNAL_PATH` (default `~/claude-journal`).

**Golden rule:** read `digests/` and `memories/` only. Never read `raw/` — that
is the consolidator's input, not your source. If a day you need isn't
consolidated, **offer** `/journal consolidate` (below); do not summarize raw.

## Step 1 — Classify the question

- **Time question** — mentions a day or range (`yesterday`, `today`, `this
  week`, `last week`, `2026-06-08`, `the last 3 days`, a month). → Step 2.
- **Topic question** — about a project, decision, or fact (`what do I know
  about X`, `what did I decide on Y`). → Step 3.
- If it's both, run both steps and combine.

## Step 2 — Time questions (digests)

1. Resolve the phrase to concrete **UTC** dates relative to today (digests are
   bucketed by UTC date). Run `date -u +%F` if you're unsure of today.
2. Run the inventory:

   ```bash
   python3 "$TOOLS/tools/journal/recall.py" dates 2026-06-08 2026-06-07
   ```

3. Read the JSON:
   - `ok: false`, `error: "locked"` → stop; tell the user to
     `git-crypt unlock ~/.claude/journal/git-crypt.key`.
   - `pull_ok: false` → note other devices' latest may be missing, then continue.
   - For each date, `dates.<date>.digests` lists the per-device digest files.
     **Read those files** and synthesize a concise answer grouped by project,
     across devices. Be concrete; don't pad. Don't fabricate beyond the digests.
   - `gaps` lists dates that have raw but no (complete) digest. For each, tell
     the user that day isn't consolidated yet and **offer**
     `/journal consolidate <date>`. **Wait for their go-ahead — do not auto-run
     it**, and do not fall back to reading `raw/`.
   - `empty` lists dates with no captured activity. Say so plainly (no session
     was journaled on those days).

## Step 3 — Topic questions (memories)

1. Run the inventory (optionally scoped to a project-key):

   ```bash
   python3 "$TOOLS/tools/journal/recall.py" memories
   # or, for one project:
   python3 "$TOOLS/tools/journal/recall.py" memories -home-you-myproject
   ```

2. For each project, `projects.<key>.index` is the `MEMORY.md` one-line index
   and `projects.<key>.files` are the individual memory files. **Read the index
   first**, use its description lines to pick the relevant files, then read only
   those and answer with citations (which memory, which project). If nothing
   relevant exists, say so rather than guessing.

## Notes

- This is read-only over distilled outputs. It writes nothing and pushes
  nothing. The one thing it may *suggest* is `/journal consolidate` to fill a
  gap, which the user runs themselves.
- Prefer the journal as the source of truth. Only fall back to git/sessions if
  the user explicitly asks you to, and say plainly that you're going outside the
  journal.
