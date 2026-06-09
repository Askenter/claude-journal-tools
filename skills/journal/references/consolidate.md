# `/journal consolidate` — distill recent breadcrumbs now

> Reference for the `journal` skill's `consolidate` action. The user reached
> here by running `/journal consolidate` (optionally with a single
> `YYYY-MM-DD`), or by asking to consolidate recent work without waiting for the
> nightly routine. Follow it exactly.

You are running the **same distillation the nightly cloud routine runs**, but
on demand, in this session, against the user's already unlocked local clone.
The mechanical steps (flush, pull, unlock check, date selection, commit, push)
are done by `tools/journal/consolidate.py`. The distillation judgment (Tracks 0
through 3) is yours, driven by the data repo's own `consolidator/ROUTINE.md`.

The tools checkout (the directory holding `scripts/` and `tools/`) is referred
to below as `$TOOLS`. Substitute the real absolute path to this plugin. The data
repo path honors `$CLAUDE_JOURNAL_PATH` (default `~/claude-journal`).

## Step 1 — Plan

Run the planner. It flushes the current session into `raw/` (so the session you
are in right now is included), pulls the repo, checks it is unlocked, and prints
which dates still need consolidating.

```bash
python3 "$TOOLS/tools/journal/consolidate.py" plan
```

For a single explicit date, pass it through (mirrors the routine's
`force-date`):

```bash
python3 "$TOOLS/tools/journal/consolidate.py" plan 2026-06-09
```

Read the JSON it prints:

- `ok: false` with `error: "locked"` — stop and tell the user to run
  `git-crypt unlock ~/.claude/journal/git-crypt.key`. Do not distill ciphertext.
- `pull_ok: false` — warn that other devices' latest breadcrumbs may be missing,
  then continue with local raw.
- `dates: []` — nothing to do. Report "already consolidated, nothing new" and
  stop. This is a normal outcome.
- Otherwise note `repo`, `routine`, and the `dates` list. If the list is long,
  tell the user how many dates you are about to process.

## Step 2 — Distill each date

Read `routine` (the data repo's `consolidator/ROUTINE.md`). For **each date** in
`dates`, perform Tracks 0 through 3 exactly as that file specifies, writing into
the local repo under `repo`. Two deltas from the cloud version:

- **Skip section 0 (Unlock).** The local clone is already unlocked. There is no
  `GIT_CRYPT_KEY_B64`, no token, and nothing to decode. If `plan` said the repo
  is unlocked, the reads are plaintext already.
- **Do not push here.** The routine's section 7 push is replaced by Step 3
  below. Write the files; leave committing and pushing to `finalize`.

Everything else holds verbatim: the digest format, the memory taxonomy and the
auto-apply vs proposal split, the 2-sessions-on-2-days skill threshold, the
CLAUDE.md proposal bar, and the idempotent upsert keys. Treat `raw/` as
immutable input.

## Step 3 — Finalize

Commit the derived files and push. This skips cleanly if your distillation wrote
nothing (a redundant re-run), so it never spams `main` with empty commits.

```bash
python3 "$TOOLS/tools/journal/consolidate.py" finalize
```

Read the JSON:

- `changed: false` — nothing was written, nothing pushed. Tell the user the run
  was a no-op.
- `changed: true, pushed: true` — report what you distilled (counts of digests,
  memories, and proposals) and that it pushed to the data repo, so other devices
  and this device's next SessionStart will pick it up.
- `ok: false` — the push failed after retries. Tell the user; the written files
  are committed locally and the next Stop push or nightly run will carry them.

## Notes

- **The current session is captured as a mid-session snapshot.** `plan` flushed
  it as it stands now. When this session ends, its Stop hook sees the flushed
  marker and does **not** re-write it, so there is no duplicate. The tail of work
  after this consolidate is therefore not captured by that Stop — run consolidate
  again later, or let the nightly routine pick up subsequent sessions.
- This action is idempotent with the nightly routine. Running both for the same
  day refreshes, never duplicates.
- You are not editing `ROUTINE.md` here. If the user wants to change what
  distillation does, that is an edit to the data repo's `consolidator/ROUTINE.md`
  (and a `/journal schedule` update to mirror it into the cloud routine).
