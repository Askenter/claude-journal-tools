# Journal consolidator routine

This is the prompt body for the nightly Phase 2 consolidator — a Claude Code
routine created once per account with `/schedule`. It runs in Anthropic's
cloud, not on any device. This file is the **source of truth**; the copy in
the routine config at `claude.ai/code/routines` must be kept in sync with it.

> This is a generic starting template seeded by `journal-bootstrap`. Tune the
> distillation rules to your taste, then paste the updated body back into the
> routine config.

## Environment contract

- `GIT_CRYPT_KEY_B64` — base64 of your git-crypt symmetric key. Required to
  decrypt the data repo. Keep it secret.
- The data-repo clone URL is provided to the routine at creation time (the
  `/schedule create … clone <url>` step).

## Procedure

1. **Clone the data repo** (the routine starts from a clean cloud checkout).
2. **Unlock it:** write `GIT_CRYPT_KEY_B64` (base64-decoded) to a temp file,
   then `git-crypt unlock <that file>`. Never echo the key to logs.
3. **Pick the target date:** *yesterday in UTC* (`date -u -d 'yesterday' +%F`,
   or the `force-date=YYYY-MM-DD` value if the run was triggered with one).
4. **Gather input:** list `raw/*/<target-date>/*.json` across all devices.
   If there are none, commit nothing and exit cleanly.
5. **Per-device digests:** for each device, write
   `digests/<target-date>/<device>.md` — a one-page summary of what that
   device worked on.
6. **Three-track distillation:**
   - **Track 1a — facts** (`user`/`project`/`reference` memories): write/update
     `memories/<project>/*.md` and the `MEMORY.md` index. Auto-applied; the
     SessionStart hook syncs them to each device. Merge overlapping
     same-day entries; keep genuine contradictions as both with a
     `<!-- conflict -->` marker.
   - **Track 1b — feedback** (behavioral rules): do NOT auto-apply. Write a
     proposal to `proposals/<target-date>-<project-key>.md` with the proposed
     rule text + a rationale citing the driving breadcrumbs.
   - **Track 2 — skills:** only canonize a technique referenced by **≥2
     sessions on different days**. Write `skills/global/<name>/SKILL.md`
     (cross-project) or `skills/projects/<project>/<name>/SKILL.md`, and
     append a line to `CHANGELOG.md`.
   - **Track 3 — CLAUDE.md / existing-skill edits:** write a proposal to
     `proposals/<target-date>-<project-key>.md` containing the target file
     path, a unified diff, and a rationale. Never auto-apply.
7. **Changelog:** append one line per Track-2/Track-3 artifact to `CHANGELOG.md`.
8. **Commit & push** to the default branch.
9. **On failure:** retry up to 3 times with exponential backoff. After the
   third failure, open a GitHub issue on the data repo with the error
   details and stop. Yesterday's raw breadcrumbs are preserved, so the next
   run picks them up.

## Guardrails

- Treat everything under `raw/` as immutable. Read it; never edit or delete it.
- `feedback` memories and CLAUDE.md/skill edits are *instructions* that change
  Claude's behavior — they always go through the proposal queue, never
  auto-apply.
- The `consolidator/` directory (this file) is intentionally NOT encrypted so
  the routine can read its own prompt from a fresh checkout.
