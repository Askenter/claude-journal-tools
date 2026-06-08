---
name: journal-schedule
description: Use when the user runs `/journal-schedule` (or asks to "create/schedule the journal consolidator routine"). Creates the once-per-account nightly Phase 2 consolidator routine via Claude Code's `/schedule`, idempotently and with a confirmation gate. Run this once, after bootstrapping the data repo.
---

You are setting up the **consolidator routine** — the once-per-account
Phase 2 step that runs in Anthropic's cloud, distilling every device's
breadcrumbs into digests/memories/skills/proposals. It is created with Claude
Code's built-in `/schedule` command. It runs **at least nightly**, and the
user may choose to run it **several times a day** so distilled output reaches
their other devices sooner (the routine is idempotent — extra runs refresh
rather than duplicate). Your job is to drive that creation safely: idempotent,
UTC-safe, with the user's explicit go-ahead on both cadence and time, and
without ever leaking the git-crypt key into the transcript.

## Preconditions (check first, bail clearly if unmet)

The data repo must already exist and be initialized (run
`/journal-setup`, or the bootstrap directly, first).
Verify, and stop with a specific message if any fails:

1. `~/claude-journal/consolidator/ROUTINE.md` exists (the routine's prompt
   source of truth). Path honors `$CLAUDE_JOURNAL_PATH` (default
   `~/claude-journal`).
2. `~/.claude/journal/git-crypt.key` exists (the key the routine needs).
3. `CLAUDE_JOURNAL_REPO_URL` is set (or discoverable via
   `git -C ~/claude-journal remote get-url origin`) — the routine clones it.
4. `~/.claude/journal/gh-token` exists — the GitHub token the cloud routine
   uses to clone **and push** the private repo (created by `/journal-setup`
   Step 4b). The cloud has no SSH key, no `gh`, and no token of its own, so
   without this the routine fails at clone with `could not read Username for
   github.com`. The repo exists by now, so verify the token actually has
   **write** access (derive `<owner>/<repo>` from the repo URL):

   ```bash
   test -f ~/.claude/journal/gh-token && \
   GH_TOKEN="$(cat ~/.claude/journal/gh-token)" \
     gh api repos/<owner>/<repo> --jq '.permissions.push'
   ```

   Stop if the file is missing (send them back to `/journal-setup` Step 4b) or
   if push is not `true` (the token lacks **Contents: Read and write** on the
   repo, or names the wrong repo). Never echo the token.

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

## Step 2 — Pick cadence, then a UTC-safe time

### 2a — How many runs per day? (ask the user)

Default is **once a day (nightly)** — the simplest, lowest-usage choice and
the right one for most people. Offer more frequent runs only if the user
wants distilled output to reach their other devices faster during the day;
the routine is idempotent, so extra runs refresh prior output instead of
duplicating it.

Two hard limits to honor when picking a cron expression:

- **Minimum interval is 1 hour.** `/schedule` rejects anything more frequent
  than hourly — never propose a sub-hourly cadence.
- **Per-account daily cap.** Anthropic caps how many routine runs start per
  account per day (currently **15 on the standard tier**; paid plans may
  differ — the live number is at claude.ai/code/routines). Keep the chosen
  cadence comfortably under the cap, and tell the user the figure so they can
  confirm it fits their plan.

Sensible presets to offer: **1/day (nightly, default)**, **2/day (~every
12h)**, **4/day (every 6h)**, **8/day (every 3h)**.

- **1/day** uses the local time you compute in 2b — `<mm> <hh> * * *`. Do
  *not* feed it through the step formula below.
- **2+/day** uses a cron hour-step: `<mm> */k * * *`, where `k = floor(24 /
  runs)` (so 2→12, 4→6, 8→3; `k` must be ≥ 1, i.e. ≤ 24 runs, but the daily
  cap binds first). The hours fire at multiples of `k` from `00` (e.g.
  `*/6` → 00,06,12,18); only the **minute** `<mm>` carries over from 2b's
  base time — the base *hour* doesn't appear in a stepped expression.

At least one run must land **after UTC midnight** so the previous day is fully
consolidated. Any `*/k` hour step guarantees this (consecutive runs are ≤ `k` ≤
12h apart, so one always falls within 12h after UTC midnight); for the
once-a-day case, the post-midnight time you compute in 2b guarantees it.

### 2b — UTC-safe base time

The routine's default window is **yesterday + today in UTC**, so the
once-a-day run must fire *after* UTC midnight or yesterday is never fully
consolidated. `/schedule` takes a **local** time, and the local→UTC gap
shifts by an hour across DST, so you must validate against the timezone's
*maximum* offset (its DST offset).

Compute, don't guess. Use Python:

```bash
python3 - <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import os


def system_zone():
    # Resolve the IANA zone NAME so ZoneInfo is DST-aware. The old
    # datetime.now().astimezone().tzinfo fallback returns a FIXED-offset tz
    # whose utcoffset() ignores the date, which silently collapses the
    # Jan-vs-Jul check below on macOS/RHEL (no /etc/timezone there).
    if os.environ.get("TZ"):
        return ZoneInfo(os.environ["TZ"])
    p = Path("/etc/timezone")          # Debian/Ubuntu convention
    if p.exists():
        return ZoneInfo(p.read_text().strip())
    link = Path("/etc/localtime")      # macOS, RHEL, Arch, Fedora, ...
    if link.is_symlink():
        return ZoneInfo(os.readlink(link).split("zoneinfo/", 1)[-1])
    raise SystemExit("cannot determine system timezone — pass it explicitly")


tz = system_zone()
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

Default to **03:30 local** for the once-a-day case, and bump later only if
the timezone's DST offset would push the run to UTC midnight or earlier.
Treat the design spec's canonical `0 3 * * *` (03:00 UTC) as the anchor
window. For a multi-run cadence, anchor the `*/k` step at that base hour's
minute (e.g. 4/day from a 03:30 base → `30 */6 * * *`) so one run lands in
the post-midnight window and the rest space evenly across the day.

## Step 3 — CONFIRM with the user before creating

This creates a recurring, autonomous cloud routine that consumes usage every
night. Show the user, in one block, exactly what you're about to do:

- routine name: `journal-consolidator`
- chosen cadence (runs per day) and the cron expression it maps to, plus the
  per-account daily cap so they can confirm it fits their plan
- chosen local run time(s) + their UTC equivalent (winter and summer)
- data repo URL it will clone
- that it needs the git-crypt key in `GIT_CRYPT_KEY_B64`
- that it clones and pushes over HTTPS using the scoped GitHub token in
  `~/.claude/journal/gh-token`, injected as `GH_TOKEN` (never shown)

Ask them to confirm (or adjust the cadence/time). **Do not proceed without a
yes.**
If they decline, stop and leave nothing created.

## Step 4 — Create the routine (keep the key out of the transcript)

Construct the create command so the key is **expanded by the shell at
runtime, never typed**. Use `$(base64 …)` command substitution — your
transcript shows the substitution, not the secret:

```bash
claude -p --bare \
  --allowedTools "Bash,Read" \
  "/schedule create a routine named 'journal-consolidator' that runs \
<SCHEDULE>. The routine prompt is the contents of \
~/claude-journal/consolidator/ROUTINE.md. It needs two environment variables: \
GIT_CRYPT_KEY_B64 set to $(base64 -w0 ~/.claude/journal/git-crypt.key), and \
GH_TOKEN set to $(cat ~/.claude/journal/gh-token). Before running it should \
clone the private data repo over HTTPS using that token: \
git clone https://x-access-token:\$GH_TOKEN@github.com/<OWNER>/<REPO>.git \
— the same token then authenticates the routine's git push."
```

- Substitute `<SCHEDULE>` and `<OWNER>/<REPO>` yourself. For the once-a-day
  default, `<SCHEDULE>` is `at <LOCAL_TIME> in my local timezone`; for a
  multi-run cadence, `<SCHEDULE>` is `on the cron schedule '<CRON>'` (e.g.
  `'30 */6 * * *'` for 4×/day). Derive `<OWNER>/<REPO>` from `CLAUDE_JOURNAL_REPO_URL`
  (the HTTPS clone URL is always `https://github.com/<owner>/<repo>.git`, even
  if the configured URL is SSH).
- **Two different expansions, deliberately.** Leave `$(base64 …)` and
  `$(cat …)` literal so *your local shell* expands them at runtime (the secret
  values are substituted into the live process, not typed into the transcript).
  But escape `\$GH_TOKEN` in the clone URL so it passes through literally and is
  expanded by the *cloud routine* at clone time — if you drop the backslash your
  local shell expands it (to empty) and the cloud gets no token.
- On macOS, `base64` has no `-w0` flag — drop it (`$(base64 ~/.claude/...)`).
- **Never** run a command that prints either secret (no bare `base64 …` / `cat
  ~/.claude/journal/gh-token`, no `echo` of `GIT_CRYPT_KEY_B64` or `GH_TOKEN`).
  If a step would surface a raw secret, redact it.

## Step 5 — Verify and report

Run `claude -p --bare "/schedule list"` again and confirm
`journal-consolidator` now appears. Report to the user:

- the routine name, its cadence (runs/day + cron), local time, and UTC
  equivalent
- that the prompt mirror lives in the cloud config and the **canonical**
  source is `~/claude-journal/consolidator/ROUTINE.md` — if they edit that
  file, they must paste the new body into the routine via `/schedule update`
- a reminder to enable **"Allow unrestricted branch pushes"** on the data
  repo so the routine can commit to `main` (otherwise devices won't see its
  output via `git pull`)

## Guardrails

- The routine is **once per account** (one routine, however many times a day
  it runs). Never create a duplicate — always do the Step 1 list check first.
- Respect the platform limits: never propose a cadence finer than hourly
  (`/schedule` rejects it) or one that would exceed the user's per-account
  daily run cap (≈15/day on the standard tier). When unsure, default to once
  a day.
- Never let the raw git-crypt key (or its base64) appear in the transcript or
  any echoed command. Use command substitution; redact if anything leaks.
- Same for the GitHub token: inject it via `$(cat ~/.claude/journal/gh-token)`
  substitution, never type or `echo` its value or `GH_TOKEN`. The token grants
  write access to the data repo — treat it exactly like the key.
- This is a consequential, recurring, cloud-side action. The Step 3
  confirmation is mandatory — do not skip it even if the user seems eager.
- You are not editing `ROUTINE.md` here. If the user wants to change what the
  routine *does*, that's an edit to the file in the data repo, then a
  `/schedule update` to mirror it.
