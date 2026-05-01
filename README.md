# claude-journal-tools

Code that powers the personal cognitive-consolidation pipeline: per-device
Stop/SessionStart hooks that push session breadcrumbs to the
[claude-journal](https://github.com/askenter/claude-journal) data repo.

Phase 1 (this repo's current scope): structural breadcrumbs only — no
in-hook LLM. The central nightly Anthropic-cloud routine (Phase 2) does
the LLM-driven distillation across all devices' breadcrumbs, and is
scheduled with Claude Code's `/schedule` (see
[Phase 2 consolidator via `/schedule`](#phase-2-consolidator-via-schedule)).

## Layout

```
claude-journal-tools/
├── tools/journal/      hook implementation, breadcrumb model, push/pull, init
├── tests/journal/      pytest suite (stdlib only, ~28 tests)
├── scripts/            init-journal-device.sh
├── skills/journal/     /journal slash-command skill (accept/skip/edit proposals)
└── docs/               design spec + phase plans
```

## First-time setup on a device

```bash
git clone git@github.com:askenter/claude-journal-tools.git ~/claude-journal-tools
cd ~/claude-journal-tools
python3 -m venv venv
venv/bin/python -m pip install pytest   # only needed for running tests
./scripts/init-journal-device.sh <device-name>
```

The init script:
- clones [claude-journal](https://github.com/askenter/claude-journal) to `~/claude-journal`
- attempts `git-crypt unlock ~/.claude/journal/git-crypt.key` (warns if absent)
- records the device name at `~/.claude/journal/device-name`
- symlinks hook entrypoints into `~/.claude/hooks/`
- registers them under Stop and SessionStart in `~/.claude/settings.json`

Re-running the script is safe (idempotent).

## Unlocking the journal repo

The `claude-journal` data repo is encrypted at rest with git-crypt
(see [its `SECURITY.md`](https://github.com/askenter/claude-journal/blob/main/SECURITY.md)
for the encrypted-vs-plaintext directory split and threat model).

After cloning, transfer the symmetric key from your password manager to
`~/.claude/journal/git-crypt.key` (`chmod 600`) and run:

```bash
git-crypt unlock ~/.claude/journal/git-crypt.key
```

Without this step, `raw/`, `digests/`, `memories/`, `skills/`,
`proposals/`, and `state/` are ciphertext on disk. The Stop hook still
pushes safely (writes are re-encrypted by git filters), but pulled
memories and proposals will be unreadable. The SessionStart hook prints
a loud `additionalContext` warning when the repo is locked.

Install git-crypt before running the init script:

```bash
# Oracle Linux / RHEL: sudo dnf --enablerepo=ol9_developer_EPEL install -y git-crypt
# Debian/Ubuntu:       sudo apt-get install -y git-crypt
# macOS:               brew install git-crypt
```

---

## Agent quickstart (Claude Code, non-interactive)

This section is written for an autonomous agent running inside Claude
Code (e.g. invoked via `claude -p "<prompt>"`) that needs to provision
this pipeline on a fresh device end-to-end. Run each step from the
user's home directory unless noted, and verify the success condition
before moving on.

> Pre-flight requirements the agent should confirm exist on the host:
> `git`, `git-crypt`, `python3.11+`, `gh` (authenticated), and the
> `claude` CLI on `$PATH`. If any are missing, install them first
> using the platform package manager — do not skip git-crypt.

### 1. Clone both repos

```bash
gh repo clone askenter/claude-journal-tools ~/claude-journal-tools
gh repo clone askenter/claude-journal       ~/claude-journal
```

Success: both directories exist and `git -C <each> status` runs cleanly.

### 2. Place the git-crypt key, then unlock

The agent cannot fabricate this key — the user must hand it over (e.g.
pasted into the session, retrieved from their password manager via a
separate skill, or copied from another device the agent has SSH access
to). Once available:

```bash
mkdir -p ~/.claude/journal && chmod 700 ~/.claude/journal
install -m 600 /dev/stdin ~/.claude/journal/git-crypt.key  # paste key contents
git -C ~/claude-journal git-crypt unlock ~/.claude/journal/git-crypt.key
```

Success: `head -1 ~/claude-journal/raw/*/*/*.json 2>/dev/null` returns
readable JSON, not binary garbage.

### 3. Run the device init script

```bash
cd ~/claude-journal-tools
python3 -m venv venv
venv/bin/python -m pip install pytest
./scripts/init-journal-device.sh "$(hostname -s)"
```

Success: `~/.claude/hooks/journal-on-stop.py` and `journal-on-start.py`
are symlinks pointing into this repo, and `~/.claude/settings.json`
lists them under both `Stop` and `SessionStart` hook arrays.

### 4. Smoke-test the hooks

End any current Claude Code session and start a new one. The
SessionStart hook should pull `~/claude-journal` silently. End that new
session; the Stop hook should write
`~/claude-journal/raw/<device>/<YYYY-MM-DD>/<session_id>.json` and
`.transcript.md`, then commit and push.

```bash
ls -lt ~/claude-journal/raw/$(cat ~/.claude/journal/device-name)/$(date -u +%F)/ | head
```

If the breadcrumb is missing, run `pytest tests/journal/` and check for
hook errors in `~/.claude/journal/hook-errors.log`.

### 5. Schedule the nightly consolidator

Continue to the next section. The consolidator only needs to be
scheduled **once per user account** (it runs in Anthropic's cloud, not
on this device), so skip this step on additional devices.

---

## Phase 2 consolidator via `/schedule`

The nightly consolidator is a Claude Code routine — a scheduled remote
agent created with the built-in `/schedule` slash command. Its prompt
lives at `~/claude-journal/consolidator/ROUTINE.md` and it expects a
base64-encoded git-crypt key in the environment variable
`GIT_CRYPT_KEY_B64`.

### Creating the routine from the CLI

`/schedule` takes free-form natural language, not positional arguments.
An agent should describe what to run and when in one sentence:

```bash
claude -p --bare \
  --allowedTools "Bash,Read" \
  "/schedule create a nightly routine named 'journal-consolidator' \
that runs at 03:30 in my local timezone. The routine prompt is the \
contents of ~/claude-journal/consolidator/ROUTINE.md. It needs the \
environment variable GIT_CRYPT_KEY_B64 set to <BASE64_KEY> and should \
clone https://github.com/askenter/claude-journal before running."
```

Replace `<BASE64_KEY>` with `base64 -w0 ~/.claude/journal/git-crypt.key`
output (treat that string the same as the raw key — never echo it to
shared logs). Drop `-w0` on macOS where `base64` wraps by default with
no flag.

> **Schedule timing — read this.** The routine treats "target date" as
> *yesterday in UTC*. Pick a local time that is unambiguously past UTC
> midnight year-round, including DST shifts, or you will get
> off-by-one digests. For Europe/Athens (UTC+2/+3) anything ≥ 03:00
> local is safe; for Pacific timezones any time after 17:00 PST works.

### Verifying and editing the routine

```bash
# List routines visible to this account
claude -p --bare "/schedule list"

# Open one for inspection or edits (cron expression, prompt body, env)
claude -p --bare "/schedule update journal-consolidator"
```

If `/schedule create` returns a non-cron cadence (e.g. "daily at 3:30am
local") and the agent needs a precise cron expression, follow up with
`/schedule update` — that path supports raw cron syntax (minimum
1-hour interval).

### Where routines live on disk

- **Source of truth:** the user's Anthropic cloud account, viewable at
  `claude.ai/code/routines`.
- **Local cache:** `~/.claude/scheduled-tasks/<routine-name>/SKILL.md`,
  editable for prompt tweaks; the cloud copy still wins on conflicts.

To remove a routine, the agent can use `/schedule delete
journal-consolidator` from the CLI, or delete it from the web console.

### What the routine produces

After it runs successfully, the data repo gains:

- `digests/<YYYY-MM-DD>/<device>.md` — per-device daily digest
- `memories/<project-key>/*.md` — distilled per-project memories (also
  auto-copied into `~/.claude/projects/<project>/memory/` on next
  SessionStart)
- `skills/*` — distilled reusable skills
- `proposals/<YYYY-MM-DD>-<project-key>.md` — pending feedback /
  CLAUDE.md proposals, surfaced at SessionStart and resolved via
  `/journal accept|skip|edit` (see `skills/journal/SKILL.md`).

---

## Updating the pipeline on existing devices

```bash
git -C ~/claude-journal-tools pull
git -C ~/claude-journal       pull
```

Hooks update automatically because `~/.claude/hooks/journal-*.py` are
symlinks into the tools repo. No re-install needed unless the init
script itself changes (in which case re-run it; it's idempotent).
