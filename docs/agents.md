# For agents

You are an AI coding agent working on a machine where the **claude-journal**
pipeline is installed. This page tells you how to *use* it correctly. If you are
a human, read it too — it explains what Claude sees and why.

## What this means for you

A background pipeline captures a breadcrumb from each Claude Code session,
distills them nightly, and feeds the results back. You benefit from it and you
participate in it. Concretely:

- **Distilled facts appear automatically.** At SessionStart, the hook mirrors
  the consolidator's distilled *memories* onto this device — per-project facts
  under `~/.claude/projects/<project-key>/memory/`. Treat them as established
  context.
- **New skills are suggested, not auto-installed.** The consolidator *proposes*
  net-new skills through the proposal queue; one becomes available only after
  you `/journal accept` it — then it syncs to your other devices automatically.
  Accepted skills live under `~/.claude/skills/` (global) or a project's
  `.claude/skills/` (project-scoped).
- **Proposals may be waiting.** If the SessionStart hook found pending
  proposals for the current project, you'll see a system reminder like
  *"📓 claude-journal has pending proposals…"*. Those are behavior changes the
  consolidator suggests but is not allowed to apply on its own.

## Golden rule: read distilled outputs, never raw transcripts

The pipeline produces four kinds of distilled artifact. **These are the only
journal sources you should read** to answer questions or inform your work:

```
   READ THESE  (distilled, curated)            DO NOT READ  (raw input)
   ──────────────────────────────────          ────────────────────────────
   ~/claude-journal/memories/<project>/    ✗  ~/claude-journal/raw/**.json
   ~/claude-journal/digests/<date>/        ✗  ~/claude-journal/raw/**.transcript.md
   ~/claude-journal/skills/
   ~/claude-journal/proposals/<date>-<project>.md
```

`raw/` is the consolidator's **input**, not yours — it is large, noisy,
unredacted-beyond-secrets working material. Reading it to answer a question is
the wrong tool and a privacy footgun. If the distilled outputs don't cover what
you need, **say so and ask** — do not fall back to grepping `raw/`.

> Memories produced by the pipeline use a **Why:** / **How to apply:** structure
> in their body (the consolidator's prompt enforces that). If you update such an
> entry, preserve those lines.

## Handling proposals: `/journal accept | skip | edit`

Proposals never auto-apply. When the user runs the `/journal` skill, follow it
exactly. The three actions:

```
   /journal accept   apply every pending proposal for this project:
                       · new skill      → write its SKILL.md into the data repo's
                                          skills/<scope>/<name>/, mirror it onto
                                          this device, and record it in
                                          CHANGELOG.md + skills/INDEX.md
                       · feedback rule  → write it as a memory file under
                                          ~/.claude/projects/<proj>/memory/ +
                                          add a MEMORY.md index line
                       · CLAUDE.md edit → read the LIVE CLAUDE.md, apply the
                                          change, show the diff, confirm, save
                       · then commit + push the data repo so other devices
                         stop seeing the resolved proposal

   /journal skip     dismiss permanently; for new-skill entries also write a
                     -skill skipped CHANGELOG line + drop the INDEX row, then
                     delete the proposal file. commit/push

   /journal edit     open the proposal in $EDITOR, then ask accept or skip
```

Key safety points baked into the skill:

- **Never overwrite an existing memory** with the same name without asking.
- For CLAUDE.md edits, **always re-read the live file** and confirm the diff
  before writing — journal staleness must never cause a wrong edit.
- Don't touch proposal files for *other* projects.
- If the data-repo push fails, complete the local change anyway and tell the
  user; the next pull reconciles.

## Privacy & handling

The journal is **personal and private — it does not leave the machine.**

- Don't paste journal content (raw breadcrumbs, transcripts, memories,
  proposals) into anything that leaves this machine, and don't echo a memory
  file's contents wholesale to chat unless asked — summarize and cite the
  filename instead.
- Never print, echo, or commit the git-crypt key
  (`~/.claude/journal/git-crypt.key`) or its base64. The pipeline scrubs it from
  transcripts; don't reintroduce it.
- Treat `raw/` as immutable: never edit or delete anything under it.

## Quick decision guide

```
   Need a fact about past work / this project?
        → check ~/claude-journal/memories/<project-key>/  (and digests/)
          not raw/. If absent, ask the user.

   See a "pending proposals" reminder?
        → tell the user; act only when they run /journal accept|skip|edit.

   Asked to set up the pipeline?  → /journal-setup
   Asked to schedule the nightly routine?  → /journal-schedule

   Tempted to grep ~/claude-journal/raw/ ?
        → stop. That's the consolidator's input, not your source.
```

## Where the project key comes from

Many paths are keyed by **project key** = the absolute project directory with
`/` replaced by `-` (e.g. `/home/you/myproject` → `-home-you-myproject`). Memories,
proposals, and the device-side memory tree all use this slug, so the same
project lines up across devices.

See [reference.md](reference.md) for exact paths and formats, and
[data-flow.md](data-flow.md#proposal-lifecycle) for the full proposal lifecycle.
