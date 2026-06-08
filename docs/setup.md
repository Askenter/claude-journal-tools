# Setup

Getting from zero to a working pipeline has four one-time steps. The first two
are per-account; the last two repeat per device.

```
   ┌────────────────────────────────────────────────────────────────────┐
   │  ONCE PER ACCOUNT                     │  ONCE PER DEVICE             │
   ├───────────────────────────────────────┼──────────────────────────────┤
   │ 1. install the plugin                  │ 3. init the device           │
   │ 2. bootstrap the data repo (1st device)│    (clone + unlock + name)   │
   │ 4. schedule the consolidator           │                              │
   └────────────────────────────────────────┴──────────────────────────────┘
```

> **Read [../SECURITY.md](../SECURITY.md) before you start.** These hooks push
> your session transcripts to a git repo on every session exit. The data repo
> **must be private and git-crypt-encrypted**.

## Prerequisites

- `git`, `git-crypt`, and `python3.11+` on `PATH`
- `gh` (authenticated) — only if you let the bootstrap create the GitHub repo
- A configured git identity (`user.name` / `user.email`) — the bootstrap's
  first commit needs it. The `/journal-setup` skill checks and sets this for you.

Install `git-crypt`:

```bash
# macOS:          brew install git-crypt
# Debian/Ubuntu:  sudo apt-get install -y git-crypt
# RHEL/Oracle:    sudo dnf --enablerepo=ol9_developer_EPEL install -y git-crypt
```

## Step 1 — Install the plugin

```text
/plugin marketplace add askenter/claude-journal-tools
/plugin install claude-journal@claude-journal-tools
```

This registers the `Stop` and `SessionStart` hooks and the `/journal`,
`/journal-setup`, and `/journal-schedule` skills. The hooks do nothing useful
until you create a data repo and name the device (steps 2–3).

## Step 2 — Bootstrap the data repo (first device only)

This creates your private `claude-journal` repo, lays out the encrypted
skeleton, initializes git-crypt, **generates your key**, and seeds the
consolidator prompt.

**Easiest path — run the skill** (it checks tools, sets your git identity, signs
you into `gh` if needed, then walks you through the bootstrap):

```text
/journal-setup
```

**Manual equivalent** — exactly what the skill runs under the hood:

```bash
git clone git@github.com:askenter/claude-journal-tools.git ~/claude-journal-tools
~/claude-journal-tools/scripts/bootstrap-journal-repo.sh --repo <you>/claude-journal
#   local-only (wire the remote yourself later):  … --no-remote
```

> The bootstrap **stops and prints your git-crypt key**, then waits for you to
> type `saved`. **Put the key in your password manager immediately** — lose it
> and every transcript, memory, and proposal in the repo is permanently
> unreadable, and no new device can ever join. For automation, back it up
> out-of-band and pass `--key-backed-up`.

The bootstrap validates every precondition (git repo absence, key absence,
tools, git identity, `gh` auth) **before** writing anything, so a missing
prerequisite never leaves a half-initialized repo behind.

## Step 3 — Initialize each device

On **every** device (including the one that ran the bootstrap), point the tools
at your data repo and give the device a stable name.

```bash
export CLAUDE_JOURNAL_REPO_URL="git@github.com:<you>/claude-journal.git"

# On ADDITIONAL devices, place the git-crypt key first (out-of-band):
mkdir -p ~/.claude/journal && chmod 700 ~/.claude/journal
install -m 600 /dev/stdin ~/.claude/journal/git-crypt.key   # paste key, then Ctrl-D

# Clone (if missing), attempt git-crypt unlock, record the device name:
git clone git@github.com:askenter/claude-journal-tools.git ~/claude-journal-tools
python3 ~/claude-journal-tools/tools/journal/init_device.py "$(hostname -s)"
```

`init_device.py` reads `CLAUDE_JOURNAL_REPO_URL` (or `--repo-url`) and
`CLAUDE_JOURNAL_PATH` (default `~/claude-journal`). Re-running is safe.

```
   first device                         additional device
   ────────────                         ─────────────────
   already has the repo + key            1. receive key from password manager
   from the bootstrap                    2. install -m 600 → git-crypt.key
        │                                3. init_device.py clones + unlocks
        ▼                                     │
   init_device.py just names it              ▼
                                        device joins the loop
```

> **Manual (non-plugin) install only:** add `--register-hooks` to symlink the
> hooks + skill into `~/.claude/` and register them in `settings.json`. **Do
> not** combine `--register-hooks` with the plugin install, or every session
> pushes its breadcrumb twice.

## Step 4 — Schedule the consolidator (once per account)

The consolidator is a Claude Code routine created with `/schedule`. It runs in
Anthropic's cloud, **once for your whole account** (not per device).

**Recommended — run the skill** (idempotent, asks cadence, picks a DST-safe
time, confirms first, keeps the key out of the transcript):

```text
/journal-schedule
```

It checks whether a `journal-consolidator` routine already exists, asks **how
many times a day** to run, computes a UTC-safe run time, shows you exactly what
it will create, and only fires after you confirm.

> **How often?** Once a day (nightly) is the default and right for most people.
> Run it more frequently only if you want distilled output to reach your other
> devices sooner during the day — runs must be **≥1h apart** (Anthropic's
> minimum) and stay under your **per-account daily run cap** (≈15/day on the
> standard tier; check yours at claude.ai/code/routines). Extra runs are safe:
> every output is an idempotent upsert, so re-running a day refreshes rather
> than duplicates.

> **Timing matters.** The routine's default window is *yesterday + today in
> UTC*, so the nightly run must fire comfortably after UTC midnight year-round
> (including DST) or yesterday is never fully consolidated. The skill validates
> against your timezone's maximum (DST) offset; the default is `03:30` local.

Manage it later with:

```bash
claude -p --bare "/schedule list"
claude -p --bare "/schedule update journal-consolidator"
```

> After scheduling, enable **"Allow unrestricted branch pushes"** on the data
> repo so the routine can commit to `main` — otherwise devices won't see its
> output on the next pull.

## Unlocking the data repo (if it shows up locked)

The data repo is encrypted at rest. If a device shows the **LOCKED** warning,
transfer the key from your password manager and unlock:

```bash
mkdir -p ~/.claude/journal && chmod 700 ~/.claude/journal
install -m 600 /dev/stdin ~/.claude/journal/git-crypt.key   # paste key, Ctrl-D
git-crypt unlock ~/.claude/journal/git-crypt.key            # run inside ~/claude-journal
```

Without this, `raw/`, `digests/`, `memories/`, `skills/`, `proposals/`, and
`state/` are ciphertext on disk: the Stop hook still pushes safely (git filters
re-encrypt), but pulled memories and proposals are unreadable.

## Verify it works

Start a new Claude Code session (SessionStart pulls silently), then end it. The
Stop hook should write a breadcrumb:

```bash
ls -lt ~/claude-journal/raw/$(cat ~/.claude/journal/device-name)/$(date -u +%F)/ | head
```

You should see `<session_id>.json` and `<session_id>.transcript.md`.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| No breadcrumb after a session | hook error or push failure | check `~/.claude/journal-buffer.log`; run `pytest tests/journal/` |
| **LOCKED** warning at SessionStart | git-crypt key not applied | `git-crypt unlock ~/.claude/journal/git-crypt.key` |
| **STALE** warning at SessionStart | pull failed (dirty tree / divergence) | check the log; `git -C ~/claude-journal status` |
| Breadcrumbs pushed twice | plugin **and** `--register-hooks` both active | remove the manual hooks from `~/.claude/settings.json` |
| Bootstrap aborts on `git commit` | no git identity configured | `git config --global user.name/user.email`, or use `/journal-setup` |
| `init_device.py` errors on repo URL | `CLAUDE_JOURNAL_REPO_URL` unset | `export` it, or pass `--repo-url` |
| Consolidator never produces output | routine not scheduled, or branch-push blocked | `/schedule list`; enable unrestricted branch pushes on the data repo |

## Updating

```bash
/plugin marketplace update claude-journal-tools   # update the plugin
git -C ~/claude-journal pull                        # update the data-repo clone
```
