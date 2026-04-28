---
name: journal
description: Use when the user runs `/journal accept`, `/journal skip`, or `/journal edit` to act on pending claude-journal proposals (feedback memories or CLAUDE.md edits surfaced at SessionStart).
---

You are handling a `/journal` slash-command invocation. The journal pipeline
distills behavioral rules and CLAUDE.md edits from recent sessions into
proposal files at `~/claude-journal/proposals/<date>-<project-key>.md`. The
SessionStart hook surfaces a list of pending proposals via system reminder
when the user starts a session in an affected project.

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
   delimited by `## ` headings. Entries are typically of two shapes:

   - **feedback proposal** — contains a fenced markdown block with
     frontmatter `type: feedback`. The `body` is a behavioral rule the
     user has expressed in some recent session.
   - **CLAUDE.md edit proposal** — contains a target file path and either
     a unified diff or a prose change request.

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

   - **`skip`:** delete the proposal file from `~/claude-journal/proposals/`
     without applying anything. The user is dismissing it permanently.

   - **`edit`:** open the proposal file in the user's editor (use `Bash` to
     run `${EDITOR:-nano} <path>`). After the user closes the editor, ask
     whether they want to `accept` or `skip` the edited proposal.

4. **Commit and push the change in `~/claude-journal/`** so other devices
   see that the proposal has been resolved (file removed). Use a commit
   message like `proposal: <action> <date>-<project-key>` and `git push`.

5. **For `accept`, also** if a CLAUDE.md was edited, commit that change
   in the affected project repo separately. Do NOT push the project repo
   automatically — let the user push when they're ready.

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
