# `/journal accept | skip | edit` — resolve pending proposals

> Reference for the `journal` skill's `accept` / `skip` / `edit` actions. The
> action is the first word of the invocation argument. Follow it exactly.

You are handling a journal slash-command invocation. The journal pipeline
distills new skills, behavioral rules, and CLAUDE.md edits from recent
sessions into proposal files under the data repo's
`proposals/<date>-<project-key>.md`. The
SessionStart hook surfaces a list of pending proposals via system reminder
when the user starts a session in an affected project.

The data repo lives at `$CLAUDE_JOURNAL_PATH` (default `~/claude-journal`);
all `~/claude-journal/...` paths below mean that directory.

## What to do

The user types `/journal <action>` where `<action>` is `accept`, `skip`, or
`edit`. The argument string is in the `$ARGUMENTS` placeholder of the
slash-command frame. Apply this action to **every** pending proposal for
the current project:

1. **Resolve the proposals.** Compute the project key as
   `cwd.replace("/", "-")`. List
   `~/claude-journal/proposals/<date>-<project-key>.md` files (any date).
   If there are none, tell the user "no pending journal proposals for
   this project" and exit.

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

3. **Branch on the action:**

   - **`accept`:**
     - For feedback proposals: write the entry as a new file in
       `~/.claude/projects/<project-key>/memory/<short-snake-name>.md`
       (preserving the frontmatter), and append a one-line index entry
       to that project's `MEMORY.md`. Do NOT auto-apply if a memory with
       the same name already exists — ask the user before overwriting.
     - For CLAUDE.md edits: read the live `CLAUDE.md` for the project,
       apply the proposed change (use Edit tool with the diff or do the
       substitution by hand if it's prose), show the user the diff, and
       confirm before saving.
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
              no such row exists (proposal predates the manifest, or the
              file is missing), create the manifest using the header in the
              "Data-repo skill record formats" section below and add:
              `| <name> | <scope> | accepted | <description> | <provenance> | <today> |`
       5. Remove this new-skill entry from the proposal file.

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

   - **`edit`:** open the proposal file in the user's editor (use `Bash` to
     run `${EDITOR:-nano} <path>`). After the user closes the editor, ask
     whether they want to `accept` or `skip` the edited proposal.

4. **Commit and push the change in `~/claude-journal/`** so other devices
   see that the proposal has been resolved. Stage everything the action
   touched — the proposal change, and (for accepted/skipped skills) the new
   `skills/<scope>/<name>/` files, `CHANGELOG.md`, and `skills/INDEX.md`. Use
   a commit message like `proposal: <action> <date>-<project-key>` and
   `git push`.

5. **For `accept`, also** if a CLAUDE.md was edited, commit that change
   in the affected project repo separately. Do NOT push the project repo
   automatically — let the user push when they're ready.

## Data-repo skill record formats

Keep both files in lockstep with accept/skip so a skill's lifecycle is plainly
visible. These are maintained by hand — match the formats exactly.

**`~/claude-journal/CHANGELOG.md`** — append one dated line per event:

```
2026-06-08 ~skill proposed global/condition-based-waiting — distilled from 2 sessions on 2026-06-05, 2026-06-07
2026-06-09 +skill accepted global/condition-based-waiting
2026-06-09 -skill skipped  project:-home-you-myproject/flaky-retry
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

## Guardrails

- Never delete or modify files under `~/claude-journal/raw/`. Those are
  immutable.
- Never modify a proposal file you didn't accept/skip/edit yourself —
  there may be other proposals for other projects that you should leave
  alone.
- If the user passes an action you don't recognize (anything other than
  `accept`, `skip`, `edit`), explain the three valid actions and exit.
- If `git push` on `~/claude-journal/` fails, complete the local file
  changes anyway and tell the user — they can resolve the push manually.
  The next SessionStart will retry the pull and the proposal won't be
  surfaced again because it's been removed locally.
