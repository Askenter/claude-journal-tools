# Reference

Exhaustive reference for env vars, commands, files, data formats, hooks, and
skills. For the narrative, see [architecture.md](architecture.md) and
[data-flow.md](data-flow.md).

## Environment variables

| Variable | Default | Used by | Purpose |
| --- | --- | --- | --- |
| `CLAUDE_JOURNAL_REPO_URL` | *(required for init)* | `init_device.py` | git URL of your private data repo to clone |
| `CLAUDE_JOURNAL_PATH` | `~/claude-journal` | hooks, `paths.py`, bootstrap, init | local path of the data-repo clone |
| `CLAUDE_JOURNAL_BUFFER` | `~/.claude/journal-buffer.jsonl` | `push.py` | offline breadcrumb backlog file |
| `GIT_CRYPT_KEY_B64` | *(set on the routine)* | consolidator | base64 of the git-crypt key, to unlock in the cloud |
| `GH_TOKEN` | *(set on the routine)* | consolidator | fine-grained GitHub PAT (Contents R/W) the cloud routine uses to clone + push the private repo |
| `CLAUDE_PLUGIN_ROOT` | *(set by Claude Code)* | `hooks.json` | plugin install root used to locate hook scripts |

## Fixed local paths (not configurable)

| Path | Mode | What it is |
| --- | --- | --- |
| `~/.claude/journal/git-crypt.key` | `0600` | the git-crypt symmetric key (never committed) |
| `~/.claude/journal/gh-token` | `0600` | fine-grained GitHub PAT for the cloud routine's clone + push (never committed) |
| `~/.claude/journal/` | `0700` | dir holding the key + token + device name |
| `~/.claude/journal/device-name` | — | this device's stable name |
| `~/.claude/journal-buffer.jsonl` | — | offline breadcrumb backlog (overridable via env) |
| `~/.claude/journal-buffer.log` | — | hook error log (pull/push/extract failures) |
| `~/.claude/projects/<project-key>/memory/` | — | where distilled memories are mirrored |
| `~/.claude/skills/<name>/` | — | where global distilled skills are mirrored |
| `~/.claude/projects/<project-key>/.claude/skills/<name>/` | — | where project-scoped skills are mirrored |

## CLI entrypoints

All Python tools are stdlib-only and self-locate their imports.

### `scripts/bootstrap-journal-repo.sh` → `tools/journal/bootstrap.py`

Create and initialize a brand-new data repo (first device, once ever).

```bash
scripts/bootstrap-journal-repo.sh --repo <owner>/claude-journal   # create remote + push
scripts/bootstrap-journal-repo.sh --no-remote                     # local-only
```

| Flag | Meaning |
| --- | --- |
| `--journal-path PATH` | where to create the repo (default `$CLAUDE_JOURNAL_PATH` or `~/claude-journal`) |
| `--repo OWNER/NAME` | create this private GitHub repo as the remote and push (needs `gh`) |
| `--no-remote` | initialize locally only; mutually exclusive with `--repo` |
| `--key-backed-up` | skip the interactive "type saved" key-backup gate (automation) |

Validates **all** preconditions before any filesystem mutation: target is not
already a git repo, `~/.claude/journal/git-crypt.key` does not already exist,
required tools present, git identity configured, and (for `--repo`) `gh`
authenticated. Prints and gates on backing up the generated key.

### `scripts/init-journal-device.sh` → `tools/journal/init_device.py`

First-time per-device setup. Clones the data repo, attempts `git-crypt unlock`,
records the device name.

```bash
python3 tools/journal/init_device.py <device-name>
python3 tools/journal/init_device.py <device-name> --repo-url <url> --journal-path <path>
python3 tools/journal/init_device.py <device-name> --register-hooks   # manual (non-plugin) only
```

| Arg / flag | Meaning |
| --- | --- |
| `device` (positional) | stable name for this device (e.g. `laptop`) |
| `--repo-url URL` | data-repo git URL (default `$CLAUDE_JOURNAL_REPO_URL`) |
| `--journal-path PATH` | local clone path (default `$CLAUDE_JOURNAL_PATH` or `~/claude-journal`) |
| `--register-hooks` | manual install: symlink hooks + `journal` skill into `~/.claude/` and register in `settings.json`. **Never** use with the plugin. |

### Hook entrypoints (invoked by Claude Code, not by you)

| Script | Event | Reads (stdin) | Effect |
| --- | --- | --- | --- |
| `tools/journal/hooks/on_stop.py` | `Stop` | `{session_id, cwd, transcript_path}` | write + push breadcrumb & transcript |
| `tools/journal/hooks/on_start.py` | `SessionStart` | `{cwd, …}` | pull, sync memories/skills, surface proposals |

## Module map (`tools/journal/`)

| Module | Responsibility |
| --- | --- |
| `paths.py` | resolve repo/buffer/device-name/flushed-sessions paths from env |
| `breadcrumb.py` | the `Breadcrumb` dataclass + serialization (truncates `first_prompt` to 200) |
| `extract.py` | parse a session transcript into structural breadcrumb fields |
| `transcript.py` | extract trimmed, redacted, tail-truncated transcript markdown |
| `capture.py` | shared `capture_session()` — build breadcrumb + transcript + state snapshot, then push (used by the Stop hook and on-demand consolidate) |
| `push.py` | write breadcrumb files, commit/pull/push, offline buffer + drain |
| `pull.py` | best-effort `git pull --rebase --autostash` |
| `consolidate.py` | on-demand `/journal consolidate` orchestrator: flush the live session, compute un-consolidated dates, commit/push the distilled output |
| `flushed.py` | device-local ledger of sessions already flushed by consolidate, so the later Stop hook skips re-writing them |
| `state.py` | snapshot a project's `CLAUDE.md` into `state/` (redacted) |
| `encryption.py` | detect whether a repo is git-crypt-locked (magic-byte sniff) |
| `sync_memories.py` | mirror `memories/` → device auto-memory tree |
| `sync_skills.py` | mirror accepted `skills/` → device skills trees |
| `surface_proposals.py` | build the SessionStart proposal-context block |
| `bootstrap.py` | create a new data repo (first device) |
| `init_device.py` | per-device clone + unlock + name (+ optional hook registration; offers plugin auto-update) |
| `autoupdate.py` | enable plugin marketplace auto-update declaratively in `settings.json` (used by `/journal setup` and `init_device.py`) |

## Data formats

### Breadcrumb JSON — `raw/<device>/<date>/<session_id>.json`

```json
{
  "session_id": "abc123",
  "device": "laptop",
  "project": "-home-you-myproject",
  "started_at": "2026-06-08T09:12:33+00:00",
  "ended_at":   "2026-06-08T09:40:01+00:00",
  "files_touched": ["/home/you/myproject/main.py"],
  "skills_invoked": ["code-review"],
  "first_prompt": "help me refactor the auth module"
}
```

| Field | Source | Notes |
| --- | --- | --- |
| `session_id` | Stop payload | also the filename stem |
| `device` | `~/.claude/journal/device-name` | path-sanitized for the directory |
| `project` | `cwd` with `/`→`-` | the **project key** |
| `started_at` / `ended_at` | first / last transcript timestamps | ISO-8601 UTC; fall back to "now" |
| `files_touched` | `Edit`/`Write`/`NotebookEdit` `file_path` inputs | de-duplicated, in order |
| `skills_invoked` | `Skill` tool `skill` inputs | de-duplicated, in order |
| `first_prompt` | first user message | truncated to 200 chars |

### Transcript — `raw/<device>/<date>/<session_id>.transcript.md`

Markdown, **user + assistant prose only** (tool calls/results dropped),
tail-truncated to **~30 KB** (older content dropped first). Best-effort secret
redaction runs over the prose — defense-in-depth behind git-crypt, **not** a
guarantee (see [SECURITY.md](../SECURITY.md#secret-handling-in-pushed-text)).
Patterns scrubbed: Anthropic/OpenAI `sk-…`, Stripe `sk_/rk_…`, the GitHub token
family (`ghp_/gho_/ghu_/ghs_/ghr_…`, `github_pat_…`), Google `AIza…` and
`GOCSPX-…`, AWS access-key ids and labelled secret keys, Slack `xox…` tokens and
webhook URLs, `Authorization: Bearer …`, database URIs with embedded
credentials, JWTs, PEM private-key blocks, and the base64 git-crypt key prefix
(`AEdJVENSWVBU…`). Format:

```markdown
## User

help me refactor the auth module

## Assistant

Sure — let's start by …
```

### Proposal — `proposals/<YYYY-MM-DD>-<project-key>.md`

One file per project per day; entries split by `## ` headings. Each entry is one
of: a **new-skill** suggestion, a **feedback** rule, or a **CLAUDE.md edit**.
SessionStart labels them by inspecting the heading/body:

| Label | Detected by |
| --- | --- |
| `new skill` | heading starts with "new skill", or body has `kind: new-skill` |
| `feedback rule` | "feedback" in heading, or body has `type: feedback` |
| `CLAUDE.md edit` | "claude.md" in heading/body, or body has `target:` |
| `proposal` | anything else |

**New-skill proposal entry** — one `## `-delimited entry (`FENCE4` = a line of
exactly four backticks, so a `SKILL.md` body with its own ``` blocks
round-trips intact):

    ## New skill: <skill-name>

    - **kind:** new-skill
    - **scope:** global            # or  project:<project-key>
    - **target:** skills/global/<skill-name>/SKILL.md
    - **provenance:** distilled from 2 sessions on 2026-06-05, 2026-06-07
    - **rationale:** <one paragraph citing the driving breadcrumbs>

    FENCE4 markdown
    ---
    name: <skill-name>
    description: <when-to-use, description-gated>
    ---
    <full SKILL.md body>
    FENCE4

`scope` (not the filename) decides where `/journal accept` installs it; a
global-scope skill is filed in the proposal of the project that produced it.

### Skill ledger — `CHANGELOG.md` (repo root, plaintext)

Append-only, one dated line per lifecycle event. `~` proposed (written by the
consolidator), `+` accepted, `-` skipped (both written by `/journal`):

```
2026-06-08 ~skill proposed global/condition-based-waiting — distilled from 2 sessions on 2026-06-05, 2026-06-07
2026-06-09 +skill accepted global/condition-based-waiting
2026-06-09 -skill skipped  project:-home-you-myproject/flaky-retry
```

### Skill manifest — `skills/INDEX.md` (encrypted)

Current state of every proposed/accepted skill. The consolidator inserts a
`proposed` row; `/journal accept` flips it to `accepted`; `/journal skip`
removes the row (the ledger keeps the skip event).

| Skill | Scope | Status | Description | Provenance | Updated |
|---|---|---|---|---|---|
| condition-based-waiting | global | accepted | Wait on a condition, never a sleep | 2 sessions: 2026-06-05, 2026-06-07 | 2026-06-09 |

> `CHANGELOG.md` and `skills/INDEX.md` are maintained **by hand** in the exact
> formats above — the cloud consolidator and the device-side `/journal` skill
> each edit them directly; there is no shared code helper. See the
> [skill-proposals spec](specs/2026-06-08-skill-proposals-design.md).

### Memory file — `memories/<project-key>/<slug>.md`

Auto-memory format with frontmatter; one fact per file, indexed by `MEMORY.md`.
`type: feedback` memories are **never** auto-synced (they belong in proposals).

```markdown
---
name: deploy-script-location
description: where the deploy script lives
metadata:
  type: project        # user | feedback | project | reference
---

The deploy script is at scripts/deploy.sh; it needs DEPLOY_ENV set.
```

## Encryption

| Aspect | Detail |
| --- | --- |
| Mechanism | `git-crypt` (symmetric) |
| Encrypted dirs | `raw/ digests/ memories/ skills/ proposals/ state/` |
| Plaintext (not encrypted) | `consolidator/` (routine reads its prompt while locked); repo-root files like `CHANGELOG.md`, `README.md`, `.gitattributes`. Note `skills/INDEX.md` **is** encrypted — it lives under `skills/`. |
| Magic prefix | `\x00GITCRYPT` (9 bytes) — used only to *detect* lock state |
| Key location | `~/.claude/journal/git-crypt.key` (`0600`), outside any repo |
| Key transfer | out-of-band (password manager); never committed or logged |
| Cloud unlock | routine decodes `GIT_CRYPT_KEY_B64` to a temp file, `git-crypt unlock` |

## Hooks wiring (`hooks/hooks.json`)

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command",
        "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/tools/journal/hooks/on_start.py\"" } ] }
    ],
    "Stop": [
      { "matcher": "", "hooks": [ { "type": "command",
        "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/tools/journal/hooks/on_stop.py\"" } ] }
    ]
  }
}
```

The SessionStart hook returns context to Claude by writing this JSON to stdout:

```json
{ "hookSpecificOutput": { "hookEventName": "SessionStart",
                          "additionalContext": "📓 …pending proposals…" } }
```

## Skills

One skill, `journal`, dispatches on the first word of its argument. Each action
has its own flow under `skills/journal/references/`.

| Action | Invoke | What it does |
| --- | --- | --- |
| `setup` | `/journal setup` | interactive first-time data-repo bootstrap (tools, git identity, `gh` sign-in, the cloud routine's GitHub token, then runs the bootstrap) |
| `schedule` | `/journal schedule` | create/update the once-per-account consolidator routine via `/schedule` — asks cadence (1+ runs/day), idempotent, DST-safe |
| `consolidate` | `/journal consolidate [date]` | run the same distillation **now**, locally, against the auto-detected un-consolidated dates (or one explicit `YYYY-MM-DD`); flushes the current session first so it's included, then commits + pushes |
| `accept` · `skip` · `edit` | `/journal accept` · `/journal skip` · `/journal edit` | resolve pending proposals for the current project |

> The command is bare `/journal`. Under the hood the plugin namespaces it as
> `claude-journal:journal`; the bare form works when there's no collision, the
> qualified form always disambiguates.

## Plugin & marketplace identifiers

| Field | Value |
| --- | --- |
| Marketplace | `claude-journal-tools` (`/plugin marketplace add askenter/claude-journal-tools`) |
| Plugin | `claude-journal` (`/plugin install claude-journal@claude-journal-tools`) |
| Manifest | `.claude-plugin/plugin.json` |
| Hooks | `hooks/hooks.json` |

## Tests

```bash
PYTHONPATH="$PWD" python3 -m pytest tests/journal/    # or: venv/bin/python -m pytest tests/journal/
```

Stdlib-only suite covering breadcrumb extraction, transcript trimming, push/pull
buffering, encryption detection, memory/skill sync, proposal surfacing,
bootstrap preconditions, and device init.
