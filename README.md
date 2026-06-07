# claude-journal-tools

A Claude Code plugin for a personal cognitive-consolidation pipeline:
per-device Stop/SessionStart hooks that push session breadcrumbs to **your
own** encrypted `claude-journal` data repo, plus a `/journal` skill for
resolving consolidation proposals.

> **Read [`SECURITY.md`](SECURITY.md) first.** These hooks push the contents
> of your sessions (including transcripts) to a git repo on every session
> exit. Your data repo **must be private and git-crypt-encrypted**. This
> tools repo ships no data repo and no key — you supply your own.

Phase 1 (this repo's scope): structural breadcrumbs only — no in-hook LLM.
The central nightly Anthropic-cloud routine (Phase 2) does the LLM-driven
distillation across all devices' breadcrumbs, scheduled with Claude Code's
`/schedule` (see [Phase 2 consolidator](#phase-2-consolidator-via-schedule)).

## Layout

```
claude-journal-tools/
├── .claude-plugin/
│   ├── plugin.json        plugin manifest (hooks + auto-discovered skill)
│   └── marketplace.json   marketplace entry for /plugin install
├── hooks/hooks.json       declarative Stop + SessionStart hook wiring
├── tools/journal/         hook implementation, breadcrumb model, push/pull, init
├── tests/journal/         pytest suite (stdlib only, ~28 tests)
├── scripts/               init-journal-device.sh (data-repo setup)
├── skills/journal/        /journal slash-command skill (accept/skip/edit)
└── docs/                  design spec + phase plans
```

Runtime is **Python 3.11+, standard library only** — no `pip install`, no
`node_modules`. The hooks run under whatever `python3` is on your `PATH`.

---

## Requirements

- `git`, `git-crypt`, `python3.11+` on `PATH`
- A **private** GitHub (or other git host) repo to use as your data store
- A git-crypt symmetric key, stored at `~/.claude/journal/git-crypt.key`

Install git-crypt:

```bash
# Oracle Linux / RHEL: sudo dnf --enablerepo=ol9_developer_EPEL install -y git-crypt
# Debian/Ubuntu:       sudo apt-get install -y git-crypt
# macOS:               brew install git-crypt
```

## Install (Claude Code plugin)

```text
/plugin marketplace add askenter/claude-journal-tools
/plugin install claude-journal@claude-journal-tools
```

That registers the `Stop` and `SessionStart` hooks and the
`/claude-journal:journal` skill. The hooks won't do anything useful until
you point them at a data repo and name the device — the one-time setup
below.

## One-time per-device setup

Tell the tools where your private data repo lives, then run the device init:

```bash
export CLAUDE_JOURNAL_REPO_URL="git@github.com:<you>/claude-journal.git"

git clone "$CLAUDE_JOURNAL_REPO_URL" ~/claude-journal

# Place your git-crypt key (out-of-band, e.g. from your password manager):
mkdir -p ~/.claude/journal && chmod 700 ~/.claude/journal
install -m 600 /dev/stdin ~/.claude/journal/git-crypt.key   # paste key, then Ctrl-D
git -C ~/claude-journal git-crypt unlock ~/.claude/journal/git-crypt.key

# Record this device's name (clones the repo if missing, retries the unlock):
git clone git@github.com:askenter/claude-journal-tools.git ~/claude-journal-tools
python3 ~/claude-journal-tools/tools/journal/init_device.py "$(hostname -s)"
```

`init_device.py` reads `CLAUDE_JOURNAL_REPO_URL` (or take `--repo-url`) and
`CLAUDE_JOURNAL_PATH` (defaults to `~/claude-journal`). Re-running is safe.

> If you are **not** using the plugin and want the hooks wired up the old
> way (symlinks + `~/.claude/settings.json`), add `--register-hooks`. Do
> **not** combine that with the plugin install or breadcrumbs push twice.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLAUDE_JOURNAL_REPO_URL` | *(required)* | git URL of your private data repo |
| `CLAUDE_JOURNAL_PATH` | `~/claude-journal` | local path of the data-repo clone |
| `CLAUDE_JOURNAL_BUFFER` | `~/.claude/journal-buffer.jsonl` | offline breadcrumb backlog |

## Unlocking the data repo

The data repo is encrypted at rest with git-crypt. After cloning, transfer
the symmetric key from your password manager to
`~/.claude/journal/git-crypt.key` (`chmod 600`) and run:

```bash
git-crypt unlock ~/.claude/journal/git-crypt.key
```

Without this, `raw/`, `digests/`, `memories/`, `skills/`, `proposals/`, and
`state/` are ciphertext on disk. The Stop hook still pushes safely (writes
are re-encrypted by git filters), but pulled memories and proposals are
unreadable, and the SessionStart hook prints a loud warning.

## Smoke-test

Start a new Claude Code session (SessionStart pulls your data repo silently),
then end it. The Stop hook should write
`~/claude-journal/raw/<device>/<YYYY-MM-DD>/<session_id>.json` and
`.transcript.md`, then commit and push:

```bash
ls -lt ~/claude-journal/raw/$(cat ~/.claude/journal/device-name)/$(date -u +%F)/ | head
```

If the breadcrumb is missing, run `pytest tests/journal/` and check
`~/.claude/journal-buffer.log` for hook errors.

---

## Phase 2 consolidator via `/schedule`

The nightly consolidator is a Claude Code routine created with the built-in
`/schedule` slash command. Its prompt lives at
`~/claude-journal/consolidator/ROUTINE.md` and it expects a base64-encoded
git-crypt key in the environment variable `GIT_CRYPT_KEY_B64`. It only needs
to be scheduled **once per account** (it runs in Anthropic's cloud, not on a
device).

```bash
claude -p --bare \
  --allowedTools "Bash,Read" \
  "/schedule create a nightly routine named 'journal-consolidator' \
that runs at 03:30 in my local timezone. The routine prompt is the \
contents of ~/claude-journal/consolidator/ROUTINE.md. It needs the \
environment variable GIT_CRYPT_KEY_B64 set to <BASE64_KEY> and should \
clone <your data-repo URL> before running."
```

Replace `<BASE64_KEY>` with `base64 -w0 ~/.claude/journal/git-crypt.key`
output (treat it as secret — never echo it to shared logs; drop `-w0` on
macOS).

> **Schedule timing.** The routine treats "target date" as *yesterday in
> UTC*. Pick a local time unambiguously past UTC midnight year-round
> (including DST) or you get off-by-one digests. For Europe/Athens (UTC+2/+3)
> anything ≥ 03:00 local is safe; for Pacific timezones any time after 17:00
> PST works.

```bash
claude -p --bare "/schedule list"                         # list routines
claude -p --bare "/schedule update journal-consolidator"  # edit cron/prompt/env
```

### What the routine produces

After a successful run the data repo gains:

- `digests/<YYYY-MM-DD>/<device>.md` — per-device daily digest
- `memories/<project-key>/*.md` — distilled per-project memories (auto-copied
  into `~/.claude/projects/<project>/memory/` on next SessionStart)
- `skills/*` — distilled reusable skills
- `proposals/<YYYY-MM-DD>-<project-key>.md` — pending feedback / CLAUDE.md
  proposals, surfaced at SessionStart and resolved via
  `/claude-journal:journal accept|skip|edit` (see `skills/journal/SKILL.md`).

---

## Updating

```bash
# Plugin install: update via the marketplace
/plugin marketplace update claude-journal-tools

# Data repo:
git -C ~/claude-journal pull
```

## Development

```bash
git clone git@github.com:askenter/claude-journal-tools.git
cd claude-journal-tools
python3 -m venv venv && venv/bin/python -m pip install pytest
venv/bin/python -m pytest tests/journal/
```

The `venv` is only for running the test suite — the shipped hooks and tools
import nothing outside the standard library.
