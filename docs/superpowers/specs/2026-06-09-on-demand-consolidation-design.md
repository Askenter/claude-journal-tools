# On-demand consolidation — `/journal consolidate`

Status: approved design, ready for implementation
Date: 2026-06-09

## Problem

Consolidation runs in exactly one place today, the nightly cloud routine
(`consolidator/ROUTINE.md`), once per account. There is no way to distill
recent breadcrumbs on demand, so after a meaningful session the user must wait
until the routine fires before the memories, skills, and proposals appear. The
user wants a `/journal consolidate` action that runs the same distillation now,
locally, and propagates the result.

A second requirement falls out of the first. The session the user is sitting in
is not in `raw/` yet, because the `Stop` hook is what writes a session there and
it has not fired mid session. The new action must capture the current session
first so it is included, and the later `Stop` hook must not write that same
session a second time.

## Goals

- A `/journal consolidate` action that distills every breadcrumb not yet
  distilled, including the live session, then commits and pushes.
- Reuse the nightly routine's distillation rules verbatim. No forked copy.
- Reuse the existing capture code so the live session is recorded exactly as the
  `Stop` hook would record it.
- Idempotent. Running it twice with no new work produces no commit.

## Non-goals

- Continuation detection or automatic firing. Dropped under YAGNI.
- Editing the nightly routine or its cadence.
- Capturing the live session's final tail. The flush is a mid session snapshot
  (see Snapshot semantics).

## Approach

Reuse over fork. The 500 lines of distillation rules in
`consolidator/ROUTINE.md` already define Tracks 0 through 3. The on demand action
runs the same rules, in the current session, against the already unlocked local
clone at `~/claude-journal`. Only two things differ from the cloud run. There is
no clone, token, or key step, because the local repo is already present and
unlocked. And the push is the device's ordinary `git push` instead of a token
embedded URL.

The mechanical work lives in a tested Python module so Claude never eyeballs the
`raw/` versus `digests/` diff. The LLM judgment (the actual distillation) is done
by the current session's Claude, driven by a skill reference that points at the
data repo's own `ROUTINE.md`.

## Components

### `tools/journal/capture.py` (new, shared capture)

Lifts the capture body out of `on_stop.main()` into one reusable function.

```
capture_session(payload: dict, device: str) -> bool
```

Builds the structural breadcrumb, extracts the trimmed transcript, snapshots
`CLAUDE.md` into `state/`, and pushes via `push_breadcrumb`. Best effort on
transcript and state, identical to today's `Stop` behavior. Both the `Stop` hook
and the consolidate flush call it, so capture stays single sourced. Also holds
the `_build_breadcrumb` helper and the `_log_error` logger moved from `on_stop`.

### `tools/journal/flushed.py` (new, dedup ledger)

Device-local ledger of session ids already captured on demand. One id per line
at `~/.claude/journal/flushed-sessions`.

```
read_flushed(path) -> set[str]
is_flushed(path, session_id) -> bool
mark_flushed(path, session_id, keep_last=500) -> None
```

`mark_flushed` is a no-op if the id is already present and trims the file to the
last `keep_last` ids so it cannot grow without bound.

### `tools/journal/hooks/on_stop.py` (slimmed)

Becomes a thin wrapper. Read the payload, read the device, and **before
capturing, check the flushed ledger**. If this `session_id` was already flushed
by a consolidate run, return 0 without writing anything. Otherwise call
`capture_session`. This is the Stop dedup requirement.

### `tools/journal/paths.py` (one addition)

```
flushed_sessions_path() -> Path   # ~/.claude/journal/flushed-sessions
```

### `tools/journal/consolidate.py` (new, the orchestrator)

Self-locating entrypoint like the hooks, runnable as
`python3 "$TOOLS/tools/journal/consolidate.py" <subcommand>`. Two subcommands so
the LLM distillation sits cleanly in the middle.

`plan`

1. Flush the current session. Read `CLAUDE_CODE_SESSION_ID` from the
   environment, take the cwd, resolve the live transcript path, build a Stop like
   payload, and call `capture_session`. On success mark the id via `mark_flushed`
   so the later `Stop` hook skips it. Best effort. A missing session id or
   transcript is logged and skipped, never fatal.
2. `pull_journal(repo)`, recording success or failure.
3. Assert `is_repo_unlocked(repo)`. If locked, print an error and exit non-zero
   before any distillation.
4. Compute the pending date set (below).
5. Print a JSON object on stdout for the skill to read: the repo path, the
   `ROUTINE.md` path, the date list, the pull status, and the flushed session id.

`finalize`

1. Stage the derived dirs that exist among `digests memories proposals skills
   CHANGELOG.md`.
2. If the index is clean, print "nothing to consolidate" and exit 0 (skip if
   empty, same rule as the routine's section 7).
3. Otherwise commit with an on demand message, then `git pull --rebase
   --autostash` and `git push`, retrying up to three times with backoff.

Helpers:

```
live_transcript_path(session_id, cwd=None) -> Path | None
compute_pending_dates(repo, today, lookback_days=14) -> list[str]
```

`live_transcript_path` derives `~/.claude/projects/<cwd-slug>/<sid>.jsonl` as the
fast path, then falls back to a glob `~/.claude/projects/*/<sid>.jsonl` because
the session id is globally unique, which sidesteps any project directory
sanitization quirk.

### `skills/journal/references/consolidate.md` (new)

Drives the current Claude. Run `plan`, read the JSON. If the date list is empty,
report nothing to do and stop. Otherwise read the data repo's
`consolidator/ROUTINE.md` and execute Tracks 0 through 3 for each date, with two
explicit deltas. Skip section 0 (the repo is already unlocked locally) and leave
the push to `finalize` rather than the routine's token URL push. Then run
`finalize` and report what changed.

### `skills/journal/SKILL.md` (dispatch)

Add a `consolidate` row to the action table, add it to the help block, and add it
to the frontmatter description.

## The auto-detect rule

A date is pending when either holds, scanning only `raw/` directories within a
bounded 14 day lookback.

- The date is today or yesterday in UTC. Always reprocessed, the same rolling
  window the nightly uses, so freshly finished and freshly flushed work is always
  redistilled. Idempotent upserts mean a redundant reprocess writes nothing.
- A device has `raw/<device>/<date>/*.json` but no matching
  `digests/<date>/<device>.md`. This backfills genuine gaps from days the nightly
  was down or a device synced late. Digest presence is the gap signal, so there
  is no fragile mtime or session id bookkeeping.

The 14 day bound stops a runaway backlog, and `plan` prints the count up front so
the scope is visible before any LLM work. An explicit
`/journal consolidate <YYYY-MM-DD>` overrides the auto set with a single date,
mirroring the routine's `force-date` escape hatch.

## Snapshot semantics and the Stop dedup

The flush reads the transcript as it stands mid session, so `ended_at` is roughly
now and the tool counts reflect work so far. The breadcrumb file is keyed by
`raw/<device>/<date>/<session_id>.json`, an upsert by filename.

Without dedup, the later `Stop` hook would rewrite that same path with the
complete transcript. The user asked that the writing not happen again, so the
flush marks the id and `Stop` honors the marker by exiting early. The accepted
tradeoff is that the tail after the flush is not captured by that `Stop`. The
natural use is running consolidate at the start of a new session to catch up the
one just closed, whose `Stop` already pushed and which will not be flushed again.

## Errors and guardrails

- Locked repo aborts before any distillation, pointing at `git-crypt unlock`.
- A failed pull warns that other devices' latest raw may be missing but still
  consolidates local raw.
- `finalize` carries the same git-crypt smudge care as `push.py`, the `--cached`
  index check and `--autostash`.
- `raw/` is never written by the orchestrator and never staged for deletion.
- Two pushes can occur in one run, the flush's raw push and finalize's derived
  push. Accepted, because it reuses `push_breadcrumb` untouched.

## Tests

- `tests/journal/test_flushed.py`: read, mark idempotence, trim to `keep_last`.
- `tests/journal/test_capture.py`: `capture_session` builds the breadcrumb,
  pushes, snapshots state when `CLAUDE.md` is present, tolerates a missing
  transcript.
- `tests/journal/test_consolidate.py`: `compute_pending_dates` includes today and
  yesterday, backfills a missing digest, respects the lookback bound, and returns
  empty when fully consolidated; `plan` flushes and marks the live session;
  `finalize` skips when the index is clean and commits the derived dirs otherwise;
  locked repo aborts.
- `tests/journal/test_on_stop.py`: updated for the refactor, plus a new test that
  a flushed `session_id` makes `Stop` skip the write.

## Docs

- `docs/architecture.md`: note two consolidation entry points, both running the
  same `ROUTINE.md`, and the flush plus dedup.
- `docs/data-flow.md`: add the on demand path.
- `docs/reference.md`: document `/journal consolidate [date]`.
- `README.md`: one line for the new action.
