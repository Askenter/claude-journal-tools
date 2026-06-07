---
name: journal-schedule
description: Use when the user runs `/claude-journal:journal-schedule` (or asks to "create/schedule the journal consolidator routine"). Creates the once-per-account nightly Phase 2 consolidator routine via Claude Code's `/schedule`, idempotently and with a confirmation gate. Run this once, after bootstrapping the data repo.
---

You are setting up the **nightly consolidator routine** — the once-per-account
Phase 2 step that runs in Anthropic's cloud, distilling every device's
breadcrumbs into digests/memories/skills/proposals. It is created with Claude
Code's built-in `/schedule` command. Your job is to drive that creation
safely: idempotent, UTC-safe, with the user's explicit go-ahead, and without
ever leaking the git-crypt key into the transcript.

## Preconditions (check first, bail clearly if unmet)

The data repo must already exist and be initialized (run the bootstrap first).
Verify, and stop with a specific message if any fails:

1. `~/claude-journal/consolidator/ROUTINE.md` exists (the routine's prompt
   source of truth). Path honors `$CLAUDE_JOURNAL_PATH` (default
   `~/claude-journal`).
2. `~/.claude/journal/git-crypt.key` exists (the key the routine needs).
3. `CLAUDE_JOURNAL_REPO_URL` is set (or discoverable via
   `git -C ~/claude-journal remote get-url origin`) — the routine clones it.

## Step 1 — Idempotency check (once per account, not per device)

The routine is account-level. Creating a second one means two routines racing
to push to the same repo. Before doing anything, list existing routines:

```bash
claude -p --bare "/schedule list"
```

If a routine named `journal-consolidator` already exists, **do not create
another**. Tell the user it's already scheduled, show its current time/cron,
and offer to update it instead (`claude -p --bare "/schedule update
journal-consolidator"`). Then stop.

## Step 2 — Pick a UTC-safe schedule time

The routine treats "target date" as **yesterday in UTC**, so it must run
*after* UTC midnight or you get off-by-one digests. `/schedule` takes a
**local** time, and the local→UTC gap shifts by an hour across DST, so you
must validate against the timezone's *maximum* offset (its DST offset).

Compute, don't guess. Use Python:

```bash
python3 - <<'PY'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time, os
tz = ZoneInfo(open("/etc/timezone").read().strip()) if os.path.exists("/etc/timezone") \
     else datetime.now().astimezone().tzinfo
# max offset across the year (DST), in hours:
now = datetime.now()
offs = {datetime(now.year, m, 15, tzinfo=tz).utcoffset() for m in (1, 7)}
max_off = max(offs).total_seconds() / 3600
# default 03:30 local; bump so local_time - max_off >= 00:30 UTC (30-min margin)
local_h = max(3.5, max_off + 0.5)
hh, mm = int(local_h), int(round((local_h % 1) * 60))
print(f"timezone={tz} max_utc_offset=+{max_off:g}h "
      f"-> schedule {hh:02d}:{mm:02d} local "
      f"(= {(hh - max_off) % 24:04.1f} UTC at peak DST)")
PY
```

Default to **03:30 local** and bump later only if the timezone's DST offset
would push the run to UTC midnight or earlier. Treat the design spec's
canonical `0 3 * * *` (03:00 UTC) as the target window.

## Step 3 — CONFIRM with the user before creating

This creates a recurring, autonomous cloud routine that consumes usage every
night. Show the user, in one block, exactly what you're about to do:

- routine name: `journal-consolidator`
- chosen local run time + its UTC equivalent (winter and summer)
- data repo URL it will clone
- that it needs the git-crypt key in `GIT_CRYPT_KEY_B64`

Ask them to confirm (or adjust the time). **Do not proceed without a yes.**
If they decline, stop and leave nothing created.

## Step 4 — Create the routine (keep the key out of the transcript)

Construct the create command so the key is **expanded by the shell at
runtime, never typed**. Use `$(base64 …)` command substitution — your
transcript shows the substitution, not the secret:

```bash
claude -p --bare \
  --allowedTools "Bash,Read" \
  "/schedule create a nightly routine named 'journal-consolidator' that runs \
at <LOCAL_TIME> in my local timezone. The routine prompt is the contents of \
~/claude-journal/consolidator/ROUTINE.md. It needs the environment variable \
GIT_CRYPT_KEY_B64 set to $(base64 -w0 ~/.claude/journal/git-crypt.key) and \
should clone <REPO_URL> before running."
```

- Substitute `<LOCAL_TIME>` and `<REPO_URL>` yourself; leave the
  `$(base64 …)` literal so the shell expands it.
- On macOS, `base64` has no `-w0` flag — drop it (`$(base64 ~/.claude/...)`).
- **Never** run a command that prints the key (no bare `base64 …`, no `echo`
  of `GIT_CRYPT_KEY_B64`). If a step would surface the raw key, redact it.

## Step 5 — Verify and report

Run `claude -p --bare "/schedule list"` again and confirm
`journal-consolidator` now appears. Report to the user:

- the routine name, local time, and UTC equivalent
- that the prompt mirror lives in the cloud config and the **canonical**
  source is `~/claude-journal/consolidator/ROUTINE.md` — if they edit that
  file, they must paste the new body into the routine via `/schedule update`
- a reminder to enable **"Allow unrestricted branch pushes"** on the data
  repo so the routine can commit to `main` (otherwise devices won't see its
  output via `git pull`)

## Guardrails

- The routine is **once per account**. Never create a duplicate — always do
  the Step 1 list check first.
- Never let the raw git-crypt key (or its base64) appear in the transcript or
  any echoed command. Use command substitution; redact if anything leaks.
- This is a consequential, recurring, cloud-side action. The Step 3
  confirmation is mandatory — do not skip it even if the user seems eager.
- You are not editing `ROUTINE.md` here. If the user wants to change what the
  routine *does*, that's an edit to the file in the data repo, then a
  `/schedule update` to mirror it.
