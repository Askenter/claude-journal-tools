# claude-journal-tools

A Claude Code plugin for a personal cognitive-consolidation pipeline:
per-device Stop/SessionStart hooks that push session breadcrumbs to **your
own** encrypted `claude-journal` data repo, plus a `/journal` skill for
resolving consolidation proposals.

> **Read [`SECURITY.md`](SECURITY.md) first.** These hooks push the contents
> of your sessions (including transcripts) to a git repo on every session
> exit. Your data repo **must be private and git-crypt-encrypted**. This
> tools repo ships no data repo and no key — you supply your own.
>
> Secrets are kept out of the journal by three layers: tool input/output is
> dropped entirely (only prose is kept), the remaining prose is scrubbed for
> known key shapes (API keys, tokens, PEM private keys, DB URIs, JWTs, the
> git-crypt key, …), and everything is git-crypt-encrypted at rest. This is
> defense-in-depth, **not** a guarantee — the encryption is the real boundary;
> redaction is best-effort over known patterns. See
> [SECURITY.md → Secret handling](SECURITY.md#secret-handling-in-pushed-text).

Phase 1 (this repo's scope): structural breadcrumbs only — no in-hook LLM.
The central nightly Anthropic-cloud routine (Phase 2) does the LLM-driven
distillation across all devices' breadcrumbs, scheduled with Claude Code's
`/schedule` (see [Phase 2 consolidator](#phase-2-consolidator-via-schedule)).

## Documentation

Full docs live in [`docs/`](docs/index.md) — built to be read by both humans and
agents, with ASCII diagrams throughout:

| Doc | For |
| --- | --- |
| [docs/index.md](docs/index.md) | Overview, mental model, glossary — **start here** |
| [docs/architecture.md](docs/architecture.md) | Components, the two repos, three phases, encryption boundary, repo layout |
| [docs/data-flow.md](docs/data-flow.md) | The life of a breadcrumb: capture → consolidate → propagate, with sequence diagrams |
| [docs/setup.md](docs/setup.md) | Install, bootstrap, add devices, schedule, verify, troubleshoot |
| [docs/reference.md](docs/reference.md) | Env vars, CLI entrypoints, file layout, data formats, hooks, skills |
| [docs/agents.md](docs/agents.md) | How an AI agent should use a project wired into claude-journal |

## Layout

```
claude-journal-tools/
├── .claude-plugin/
│   ├── plugin.json        plugin manifest (hooks + auto-discovered skills)
│   └── marketplace.json   marketplace entry for /plugin install
├── hooks/hooks.json       declarative Stop + SessionStart hook wiring
├── tools/journal/         hook implementation, breadcrumb model, push/pull, init
├── tests/journal/         pytest suite (stdlib only, 106 tests across 13 files)
├── scripts/               bootstrap-journal-repo.sh + init-journal-device.sh (data-repo setup)
├── skills/                the /journal slash-command skill (see below)
└── docs/                  design specs, phase plans, architecture + reference guides
```

Skills shipped under `skills/`:

- `journal/` — one command, three actions (the flows live in `journal/references/`):
  - `/journal setup` — guided first-time bootstrap of your data repo
  - `/journal schedule` — create/update the nightly Phase 2 consolidator routine via `/schedule`
  - `/journal accept|skip|edit` — resolve pending consolidation proposals

Runtime is **Python 3.11+, standard library only** — no `pip install`, no
`node_modules`. The hooks run under whatever `python3` is on your `PATH`.

---

## Requirements

- `git`, `git-crypt`, `python3.11+` on `PATH`
- `gh` (authenticated) — only if you let the bootstrap create the GitHub repo
- A **private** data repo + a git-crypt key. You can create both in one step
  with `bootstrap-journal-repo.sh` (below), or bring your own.

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

That registers the `Stop` and `SessionStart` hooks and the single `/journal`
command (`setup`, `schedule`, `accept`/`skip`/`edit`). The hooks won't do
anything useful until you create a data repo and name the device — the two
one-time steps below.

## Create your data repo (once, ever — first device only)

If you don't already have a `claude-journal` data repo, bootstrap one. This
creates the private GitHub repo, lays out the encrypted directory skeleton,
initializes git-crypt, **generates your key**, and seeds a generic
`consolidator/ROUTINE.md`.

**Easiest path:** run `/journal setup`. It checks your tools,
sets your git identity, signs you into `gh` if a remote is wanted, then walks
you through the bootstrap below (the key stays in your terminal, never the
transcript). Prefer the manual route? It's exactly what the skill runs:

```bash
git clone git@github.com:askenter/claude-journal-tools.git ~/claude-journal-tools
~/claude-journal-tools/scripts/bootstrap-journal-repo.sh --repo <you>/claude-journal
# or, to wire the remote up yourself:  ... --no-remote
```

The bootstrap **stops and prints your git-crypt key**, requiring you to
acknowledge you've saved it before any remote is created. **Save it in your
password manager immediately** — lose this key and every transcript, memory,
and proposal in the repo is permanently unreadable, and no new device can
ever join. (For automation, back it up out-of-band and pass `--key-backed-up`.)

Already have a data repo? Skip this section.

> Bootstrap only seeds the `ROUTINE.md` prompt; it does not create the cloud
> routine. After your devices are set up, run `/journal schedule`
> once to create it — see [Phase 2 consolidator](#phase-2-consolidator-via-schedule).

## One-time per-device setup

On **each** device, point the tools at your data repo and name the device:

```bash
export CLAUDE_JOURNAL_REPO_URL="git@github.com:<you>/claude-journal.git"

# On the device that ran the bootstrap, the repo already exists locally and
# is unlocked. On *additional* devices, place the key first (out-of-band):
mkdir -p ~/.claude/journal && chmod 700 ~/.claude/journal
install -m 600 /dev/stdin ~/.claude/journal/git-crypt.key   # paste key, then Ctrl-D

# Clones the repo if missing, attempts the git-crypt unlock, records the name:
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

The consolidator is a Claude Code routine created with the built-in
`/schedule` slash command, run **at least nightly** (you can schedule it
several times a day — see cadence below). Its prompt lives at
`~/claude-journal/consolidator/ROUTINE.md` and it expects a base64-encoded
git-crypt key in the environment variable `GIT_CRYPT_KEY_B64`. Because it
clones and pushes your **private** data repo from Anthropic's cloud — where no
SSH key or `gh` exists — it also needs a fine-grained GitHub token (Contents:
Read and write on that repo) in `GH_TOKEN`. It only needs to be scheduled
**once per account** (it runs in Anthropic's cloud, not on a device).

**Recommended — let Claude create it** (idempotent, UTC-safe, confirms first):

```text
/journal schedule
```

The skill checks whether a `journal-consolidator` routine already exists,
asks how many times a day to run, picks a DST-safe run time, shows you
exactly what it'll create, and only fires after you confirm. It passes the
key and the GitHub token via shell `$(…)` substitutions so neither secret ever
lands in the transcript. (`/journal setup` Step 4b mints and stores that token
at `~/.claude/journal/gh-token`.)

<details><summary>Manual equivalent (what the skill runs under the hood)</summary>

```bash
claude -p --bare \
  --allowedTools "Bash,Read" \
  "/schedule create a nightly routine named 'journal-consolidator' \
that runs at 03:30 in my local timezone. The routine prompt is the \
contents of ~/claude-journal/consolidator/ROUTINE.md. It needs the \
environment variables GIT_CRYPT_KEY_B64 set to <BASE64_KEY> and GH_TOKEN \
set to <GITHUB_TOKEN>, and before running should clone the private repo \
over HTTPS with the token: \
git clone https://x-access-token:\$GH_TOKEN@github.com/<owner>/<repo>.git \
(the same token then authenticates its push)."
```

Replace `<BASE64_KEY>` with `base64 -w0 ~/.claude/journal/git-crypt.key`
output (drop `-w0` on macOS) and `<GITHUB_TOKEN>` with
`cat ~/.claude/journal/gh-token`. Both are secrets — never echo them to shared
logs. Keep the `\$GH_TOKEN` in the clone URL backslash-escaped so the **cloud**
routine expands it, not your local shell. The token is a fine-grained PAT
scoped to the data repo with Contents: Read and write; the cloud has no other
GitHub auth, so without it the clone fails.

</details>

> **Cadence.** Once a day (nightly) is the default and right for most people.
> You can run it more often so distilled output reaches your other devices
> sooner — runs must be **≥1h apart** (Anthropic's minimum) and stay under
> your **per-account daily run cap** (≈15/day on the standard tier; check
> claude.ai/code/routines). Extra runs are safe: every output is an
> idempotent upsert, so re-running a day refreshes rather than duplicates.
>
> **Schedule timing.** The routine's default window is *yesterday + today in
> UTC*, so the nightly run must fire unambiguously past UTC midnight
> year-round (including DST) or yesterday is never fully consolidated. For
> Europe/Athens (UTC+2/+3) anything ≥ 03:00 local is safe; for Pacific
> timezones any time after 17:00 PST works.

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
  `/journal accept|skip|edit` (see `skills/journal/SKILL.md`).

---

## Updating

**The plugin.** Two steps — refreshing the marketplace alone does *not* upgrade
the installed plugin:

```text
/plugin marketplace update claude-journal-tools
/plugin update claude-journal@claude-journal-tools
```

Prefer hands-off? Enable auto-update once — `/plugin` → **Marketplaces** →
`claude-journal-tools` → **Enable auto-update** (third-party marketplaces have it
**off by default**). `/journal setup` also offers to turn this on during setup.

> New releases only appear when the **version** is bumped in
> `.claude-plugin/plugin.json` — pushing commits without a version bump is not
> seen as an update.

**The data repo.** Your distilled memories/skills/proposals sync automatically
at each SessionStart; to pull manually:

```bash
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
