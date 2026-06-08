# Data flow — the life of a breadcrumb

This page traces one piece of work end to end: from the moment you finish a
Claude Code session, through nightly distillation, to the moment a distilled
memory or proposal shows up in a future session. Read [architecture.md](architecture.md)
first for the components.

## The big loop

```
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                                                                            │
  │   you work in a session                                                    │
  │          │                                                                 │
  │          ▼  Stop event                                                     │
  │   ① CAPTURE  ──────────────► raw/<device>/<date>/<sid>.json (+ .transcript)│
  │   (on_stop.py)                                  │                          │
  │                                                 │ pushed to data repo      │
  │                                                 ▼                          │
  │   ② CONSOLIDATE (nightly, cloud) ──reads raw/<yesterday>──┐                │
  │   (consolidator/ROUTINE.md)                               │                │
  │        writes digests/ memories/ skills/ proposals/ ◄─────┘                │
  │                                                 │                          │
  │                                                 │ pushed to data repo      │
  │          ┌──────────────────────────────────────┘                         │
  │          ▼  SessionStart event (next session, any device)                  │
  │   ③ PROPAGATE ── pull ──► sync memories+skills ──► surface proposals       │
  │   (on_start.py)                                          │                 │
  │                                                          ▼                 │
  │   you run /journal accept|skip|edit on the proposals  ──────► loop repeats │
  │                                                                            │
  └──────────────────────────────────────────────────────────────────────────┘
```

---

## ① Capture — the Stop hook (`on_stop.py`)

Runs when a session ends. Always exits 0; failures degrade to a local buffer.

```
 Stop event payload (stdin JSON):
   { session_id, cwd, transcript_path }
        │
        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ 1. read device name   (~/.claude/journal/device-name)        │
 │ 2. extract_structural(transcript)  → breadcrumb fields:      │
 │        files_touched  (Edit/Write/NotebookEdit file_path)    │
 │        skills_invoked  (Skill tool 'skill' input)            │
 │        first_prompt    (first user msg, ≤200 chars)          │
 │        started_at / ended_at  (first/last timestamps)        │
 │ 3. extract_transcript_text(transcript)                       │
 │        user+assistant prose only, tail-truncated to ~30 KB,  │
 │        secrets redacted (sk-… ghp_… github_pat_… key b64)    │
 │ 4. snapshot <cwd>/CLAUDE.md → state/<project-key>/CLAUDE.md  │
 │    (best-effort; redacted)                                   │
 └─────────────────────────────────────────────────────────────┘
        │
        ▼
   push_breadcrumb()  → writes two files, then git add/commit/pull/push
        │
        ├─ success → done
        └─ failure → append {breadcrumb, transcript} to the local buffer
                     (~/.claude/journal-buffer.jsonl) for next time
```

The breadcrumb is **structural only** — it records *what* happened. The
transcript text carries *why* (decisions, preferences) and is what lets the
nightly routine extract memories and skills. Tool calls and tool results are
stripped from the transcript to keep it small and signal-dense.

### Push, with offline buffering (`push.py`)

The push is ordered carefully so a resumed session, a dirty working tree, or a
lost network can never wedge future pushes:

```
 push_breadcrumb:
   1. drain_buffer()        ── re-apply any backlogged entries first
   2. write raw/<device>/<date>/<sid>.json
   3. write raw/<device>/<date>/<sid>.transcript.md   (if transcript non-empty)
   4. git add -A raw/ state/
   5. git diff --cached --quiet?
         dirty  → git commit -m "raw: <device> <date> <sid>"
         clean  → skip commit (avoids "nothing to commit" wedge)
   6. git pull --rebase --autostash --quiet     ── merge other devices first
   7. git push
        │
        ├─ all steps ok → return True
        └─ any failure → append to buffer, return False  (retried next session)
```

Why these details matter:

- **Commit before pull.** `git pull --rebase` refuses to run with staged
  changes uncommitted, and a Stop hook can re-fire for the same `session_id`
  (resumed session). Committing first keeps `raw/` clean.
- **`--autostash`.** After `git-crypt unlock`, the smudge filter can leave
  `.gitkeep` blobs looking modified. Autostash keeps that unrelated dirt from
  aborting the rebase.
- **Check the index, not the working tree.** Step 5 inspects `--cached` so
  smudge artifacts in the working tree don't trigger an empty commit that
  exits 1.

**Buffer format** — one JSON object per line:

```json
{"breadcrumb": { …structural fields… }, "transcript": "## User\n\n…"}
```

A backlogged breadcrumb is filed under *its own* `started_at` date when drained,
so catching up days later still lands it on the right day. Errors are appended
to `~/.claude/journal-buffer.log`.

---

## ② Consolidate — the nightly routine (`consolidator/ROUTINE.md`)

One Claude Code routine, scheduled with `/schedule`, running in Anthropic's
cloud **once per account**. It is the only LLM step.

```
 nightly trigger (cron, in the cloud)
        │
        ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ 1. clone the private repo over HTTPS (GH_TOKEN, never logged)     │
 │ 2. git-crypt unlock  (key from GIT_CRYPT_KEY_B64, never logged)   │
 │ 3. dates = yesterday+today in UTC                                 │
 │ 4. gather raw/*/<target>/*.json  across ALL devices              │
 │       none? → commit nothing, exit clean                          │
 │ 5. per device → digests/<target>/<device>.md                      │
 │ 6. THREE-TRACK DISTILLATION:                                       │
 │      1a facts     → memories/<project>/*.md      (auto-apply)     │
 │      1b feedback  → proposals/<target>-<proj>.md (needs approval) │
 │      2  new skill*→ proposals/ (new-skill entry) (needs approval) │
 │                     + ~proposed line in CHANGELOG.md             │
 │                     + proposed row in skills/INDEX.md           │
 │      3  CLAUDE.md → proposals/<target>-<proj>.md (needs approval) │
 │         /skill edits                                              │
 │ 7. append CHANGELOG.md / INDEX.md records for proposed skills     │
 │ 8. git commit && git push (default branch)                        │
 │ 9. on failure: retry ×3 backoff, then open a GitHub issue & stop  │
 └──────────────────────────────────────────────────────────────────┘

   * a technique is only PROPOSED as a skill if it appears in ≥2 sessions on
     different days (one-off tricks don't become skills). Net-new skills are
     proposed, never auto-applied — see the skill-proposals spec.
```

The split between **auto-apply** (facts only) and **proposal** (new skills,
feedback rules, CLAUDE.md/skill edits) is the heart of the safety model — see
[architecture.md](architecture.md#why-facts-auto-apply-but-behavior-changes-dont).
`raw/` is treated as immutable input; a failed run loses nothing.

---

## ③ Propagate — the SessionStart hook (`on_start.py`)

Runs when any session starts on any device. Always exits 0.

```
 SessionStart event payload (stdin JSON): { cwd, … }
        │
        ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ 1. pull_journal()   git pull --rebase --autostash                 │
 │        failed? → remember it (STALE warning later)                │
 │ 2. sync_all_memories():                                            │
 │       memories/<proj>/*.md → ~/.claude/projects/<proj>/memory/     │
 │       · skips type: feedback memories (those are proposals)        │
 │       · appends NEW MEMORY.md index lines; never deletes yours     │
 │ 3. sync_all_skills():                                              │
 │       skills/global/<n>/  → ~/.claude/skills/<n>/                  │
 │       skills/projects/<p>/<n>/ → ~/.claude/projects/<p>/.claude/   │
 │                                  skills/<n>/                       │
 │ 4. build_proposal_context(cwd):                                    │
 │       list pending proposals/<date>-<project-key>.md entries       │
 │ 5. emit hookSpecificOutput.additionalContext (stdout JSON):        │
 │       [STALE warning?] + [LOCKED warning?] + [proposal list?]      │
 └──────────────────────────────────────────────────────────────────┘
        │
        ▼
   Claude's next turn sees the additionalContext as a system reminder:
   "📓 claude-journal has pending proposals for this project: …
    Run /journal accept | skip | edit"
```

Two guard warnings can be surfaced:

- **LOCKED** — the repo is encrypted on disk because the key wasn't applied.
  Fix: `git-crypt unlock ~/.claude/journal/git-crypt.key`.
- **STALE** — the SessionStart pull failed, so what you see may be out of date.
  Check `~/.claude/journal-buffer.log` and `git -C ~/claude-journal status`.

---

## Proposal lifecycle

Proposals are the human-in-the-loop part. The consolidator writes them; you
resolve them with the `/journal` skill.

```
   consolidator writes              SessionStart surfaces          you decide
   proposals/<date>-<proj>.md  ───► additionalContext block  ───►  /journal …
        │                                                              │
        │  entries split by "## " headings, each labeled:             │
        │   [new skill] [feedback rule] [CLAUDE.md edit]              │
        │                                                              ▼
        │                                          ┌──────────────────────────────┐
        │                                          │ accept → apply it:            │
        │                                          │   new skill → write SKILL.md  │
        │                                          │     to skills/<scope>/<name>/,│
        │                                          │     mirror onto this device,  │
        │                                          │     record CHANGELOG + INDEX  │
        │                                          │   feedback → write a memory   │
        │                                          │     under ~/.claude/projects/ │
        │                                          │     <proj>/memory/ + index    │
        │                                          │   CLAUDE.md edit → edit the   │
        │                                          │     live file (after diff +   │
        │                                          │     your confirm)             │
        │                                          │ skip   → record skip, delete  │
        │                                          │ edit   → open in $EDITOR,     │
        │                                          │          then accept/skip     │
        │                                          └──────────────────────────────┘
        │                                                              │
        └─────────── proposal file removed, change pushed ◄───────────┘
                     to the data repo so other devices stop seeing it
```

Nothing in a proposal is ever auto-applied. Until you `accept`, the only effect
is the one-line reminder at SessionStart. See the `/journal` skill at
`skills/journal/SKILL.md` for the exact accept/skip/edit behavior.

## Failure modes at a glance

| Situation | What happens | You see / do |
| --- | --- | --- |
| No network at Stop | breadcrumb buffered locally | nothing; drained next session |
| Push rejected (remote ahead) | rebase + retry; else buffer | nothing; drained next session |
| Repo locked (no key) | sync reads ciphertext | **LOCKED** warning → `git-crypt unlock` |
| Pull fails at SessionStart | sync uses stale local state | **STALE** warning → check the log |
| Consolidator errors 3× | raw/ kept, GitHub issue opened | fix, next night reprocesses |
| Resumed session re-fires Stop | same `session_id` rewritten cleanly | nothing (commit-before-pull handles it) |
