---
name: journal
description: Use for any claude-journal pipeline command. The user runs `/journal <action>` where `<action>` is `setup` (first-time data-repo bootstrap), `schedule` (create or update the nightly consolidator routine), `consolidate` (distill recent breadcrumbs now, on demand, including the current session, instead of waiting for the nightly run), or `accept` / `skip` / `edit` (resolve pending proposals surfaced at SessionStart). Also triggers when the user asks to set up, bootstrap, or schedule the journal / consolidation pipeline, to consolidate or distill recent work now, or to accept, skip, or edit its proposals.
---

You are handling a `/journal <action>` invocation. The **first word** of the
invocation argument (the `$ARGUMENTS` slash-command placeholder) selects the
subcommand; everything after it is that subcommand's own argument. Each flow
lives in its own reference file next to this one — read **only** the one for
the chosen action, then follow it as if it were the whole skill.

| `<action>` | What it does | Then |
| --- | --- | --- |
| `setup` | One-time, first-machine bootstrap of the `claude-journal` *data* repo (tools, git identity, `gh` sign-in, the GitHub token the cloud routine needs, then the bootstrap). | Read `references/setup.md` (relative to this skill's directory) and follow it exactly. |
| `schedule` | Create — or update — the once-per-account nightly consolidator routine via `/schedule`. | Read `references/schedule.md` and follow it exactly. |
| `consolidate` | Distill recent breadcrumbs **now**, locally, including the current session, instead of waiting for the nightly routine. Runs the same Tracks 0–3 against the auto-detected un-consolidated dates (or one explicit `YYYY-MM-DD`), then commits and pushes. | Read `references/consolidate.md` and follow it exactly. |
| `accept` / `skip` / `edit` | Resolve the pending proposals (new skills, feedback memories, CLAUDE.md edits) for the current project; pass the action through. | Read `references/resolve.md` and follow it exactly. |

Rules:

- The four references are **mutually exclusive** flows. Don't read more than
  one, and don't merge their steps.
- `setup` and `schedule` are consequential one-time actions. Their references
  carry their own confirmation gates, idempotency checks, and key/token
  guardrails — honor them; don't shortcut.
- If there is **no** action (bare `/journal`) or an unrecognized one, don't
  guess — print this help and stop:

  ```
  /journal setup              bootstrap the data repo (run once, first machine)
  /journal schedule           create or update the nightly consolidator routine
  /journal consolidate [date] distill recent breadcrumbs now (incl. this session)
  /journal accept|skip|edit   resolve pending proposals for this project
  ```
