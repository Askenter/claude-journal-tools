# Architecture

claude-journal is a loop with three stages — **capture**, **consolidate**,
**propagate** — connected by a single shared, encrypted git repository. This
page explains the moving parts and how they fit together.

## The two repositories

Keep these straight; almost everything else follows from the split.

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│  claude-journal-tools  (TOOLS REPO)  │     │  claude-journal        (DATA REPO)   │
│  — you install this; public/shareable│     │  — you own this; PRIVATE + encrypted │
├─────────────────────────────────────┤     ├─────────────────────────────────────┤
│ .claude-plugin/   plugin manifest    │     │ raw/        breadcrumbs+transcripts  │ 🔒
│ hooks/hooks.json  Stop + SessionStart│     │ digests/    per-device daily summary │ 🔒
│ tools/journal/    hook impl (stdlib) │     │ memories/   distilled facts          │ 🔒
│ skills/           the /journal skill │     │ skills/     distilled skills         │ 🔒
│ scripts/          bootstrap + init   │     │ proposals/  pending behavior changes │ 🔒
│ tests/            pytest suite       │     │ state/      CLAUDE.md snapshots      │ 🔒
│ docs/             this documentation │     │ consolidator/ROUTINE.md  (plaintext) │
│                                      │     │ .gitattributes  git-crypt filters    │
│ contains NO personal data, NO key    │     │ 🔒 = encrypted at rest via git-crypt │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

- The **tools repo** is generic code. It is safe to fork, star, and read. It
  ships no breadcrumbs and no git-crypt key.
- The **data repo** is *yours*. It must be **private** and **git-crypt-encrypted**.
  You create it once (see [setup.md](setup.md)). It is the single source of
  truth that every device and the nightly routine read from and write to.

## System overview

```
        DEVICE A  (e.g. laptop)                    DEVICE B  (e.g. workstation)
   ┌──────────────────────────────┐           ┌──────────────────────────────┐
   │ Claude Code + plugin          │           │ Claude Code + plugin          │
   │                               │           │                               │
   │  SessionStart hook  ─pull─┐   │           │   ┌─pull─  SessionStart hook  │
   │  (sync + surface)         │   │           │   │        (sync + surface)   │
   │                           │   │           │   │                           │
   │  Stop hook  ───push──┐    │   │           │   │   ┌──push───  Stop hook    │
   └──────────────────────│────│───┘           └───│───│──────────────────────┘
                          │    │                   │   │
                     push │    │ pull         pull │   │ push
                          ▼    │                   │   ▼
                   ┌──────────────────────────────────────────┐
                   │           DATA REPO  (git host)           │
                   │     github.com/<you>/claude-journal       │
                   │     private · git-crypt encrypted         │
                   │     raw/  digests/  memories/  skills/    │
                   │     proposals/  state/  consolidator/     │
                   └───────────────▲──────────────┬───────────┘
                          clone +   │              │  produces digests/,
                          unlock +  │              │  memories/, skills/,
                          push      │              │  proposals/
                                    │              ▼
                       ┌────────────┴──────────────────────────┐
                       │   PHASE 2 — CONSOLIDATOR ROUTINE       │
                       │   Claude Code /schedule routine        │
                       │   runs in Anthropic's cloud            │
                       │   ONCE PER ACCOUNT, nightly            │
                       │   prompt = consolidator/ROUTINE.md     │
                       └───────────────────────────────────────┘
```

Devices never talk to each other directly. The data repo is the only meeting
point. The consolidator is also just another client of the data repo — it
clones, reads `raw/`, writes distilled output, and pushes.

## The three phases

### Phase 1 — Capture (on each device, no LLM)

Triggered by Claude Code's **`Stop`** event at session end. The
`tools/journal/hooks/on_stop.py` entrypoint:

1. Reads the Stop payload (`session_id`, `cwd`, `transcript_path`).
2. Builds a **structural breadcrumb** by parsing the session transcript
   (`extract.py`) — files touched (from `Edit`/`Write`/`NotebookEdit`), skills
   invoked (from `Skill`), the first user prompt (truncated), and start/end
   timestamps.
3. Extracts a **trimmed transcript** (`transcript.py`) — user + assistant prose
   only, tail-truncated to ~30 KB, with best-effort secret redaction
   (see [SECURITY.md](../SECURITY.md#secret-handling-in-pushed-text)).
4. Snapshots the project's `CLAUDE.md` into `state/` (so the consolidator can
   diff against it for CLAUDE.md-edit proposals).
5. Pushes all of it under `raw/<device>/<date>/` (`push.py`). If the push
   fails, everything is appended to a local **buffer** and retried next time.

This phase runs **no LLM** — it is pure data collection, fast and offline-safe.

### Phase 2 — Consolidate (in the cloud, once per account, at least nightly)

A single Claude Code **routine** created with `/schedule` (see
`/journal schedule`). Its prompt is `consolidator/ROUTINE.md` in the data
repo (kept plaintext so the routine can read it from a fresh checkout). It runs
nightly by default — and may be scheduled several times a day, since every
output is an idempotent upsert (re-running a day refreshes, never duplicates).
Each run:

1. Clones the private data repo over HTTPS with a fine-grained GitHub token
   from `GH_TOKEN`, then unlocks it with the git-crypt key from
   `GIT_CRYPT_KEY_B64`.
2. Targets a **yesterday + today UTC** window (or a single `force-date`) and
   gathers `raw/*/<date>/*.json` from every device.
3. Writes per-device **digests**, then runs **three-track distillation**:
   - **Track 1a — facts** → `memories/<project>/*.md` (auto-applied).
   - **Track 1b — feedback rules** → `proposals/…` (needs your approval).
   - **Track 2 — new skills** (only if a technique appears in ≥2 sessions on
     different days) → a **new-skill proposal** in `proposals/…` (needs your
     approval), plus a `proposed` row in `skills/INDEX.md` and a `~skill
     proposed` line in `CHANGELOG.md`.
   - **Track 3 — CLAUDE.md / existing-skill edits** → `proposals/…` (needs
     approval).
4. Updates `CHANGELOG.md`, commits, and pushes. On repeated failure it opens a
   GitHub issue and leaves `raw/` intact for the next run.

This is the only place LLM judgment enters the pipeline, and it runs **once for
your whole account**, not once per device — so there's a single, coherent view
across machines.

#### On-demand consolidation (`/journal consolidate`)

The same distillation has a second entry point for when you don't want to wait
for the nightly run. `/journal consolidate` runs Tracks 0–3 **locally, in the
current session**, against the already-unlocked clone, driven by the data repo's
own `consolidator/ROUTINE.md` (so local and cloud stay identical — no forked
rules). It differs from the cloud run in only two ways: there's no clone/key/token
step (the local repo is already unlocked), and it pushes with the device's normal
`git push`. Before distilling, it **flushes the current session** into `raw/`
using the same `capture.py` the `Stop` hook uses, so the session you're sitting in
is included; that session id is recorded in a device-local flushed ledger
(`~/.claude/journal/flushed-sessions`) so the later `Stop` hook **doesn't write it
a second time**. The date set is auto-detected (today + yesterday always, plus any
date in a 14-day lookback whose digests are missing), and every write is the same
idempotent upsert, so on-demand and nightly runs refresh rather than duplicate.
See `tools/journal/consolidate.py` and the
[on-demand consolidation spec](superpowers/specs/2026-06-09-on-demand-consolidation-design.md).

### Phase 3 — Propagate (on each device, no LLM)

Triggered by Claude Code's **`SessionStart`** event. The
`tools/journal/hooks/on_start.py` entrypoint:

1. **Pulls** the data repo (`pull.py`, rebase + autostash).
2. **Mirrors memories** (`sync_memories.py`): `memories/<project>/*.md` →
   `~/.claude/projects/<project>/memory/`, appending new `MEMORY.md` index lines
   without clobbering device-original entries. Skips `type: feedback` memories.
3. **Mirrors skills** (`sync_skills.py`): `skills/global/<name>/` →
   `~/.claude/skills/<name>/`; `skills/projects/<project>/<name>/` →
   `~/.claude/projects/<project>/.claude/skills/<name>/`.
4. **Surfaces proposals** (`surface_proposals.py`) for the current project as
   `additionalContext`, so the next assistant turn sees them and you can
   `/journal accept|skip|edit`.
5. Emits **warnings** if the repo is locked (key not applied) or the pull
   failed (results may be stale).

Like Phase 1, this runs **no LLM** — it is file sync + a context nudge.

## Why facts auto-apply but behavior changes don't

The pipeline draws a hard line by *blast radius*:

```
   distilled artifact            destination                applied how
   ─────────────────────────────────────────────────────────────────────
   user/project/reference   →   ~/.claude/.../memory/   →   automatic
   memory (a fact)

   new skill                →   proposals/               →   /journal accept
   feedback rule            →   proposals/               →   /journal accept
   CLAUDE.md edit           →   proposals/               →   /journal accept
   edit to existing skill   →   proposals/               →   /journal accept
```

A *fact* ("the deploy script lives at X") is low-risk to surface, so it
auto-applies. Everything that changes how Claude *behaves* — a feedback rule, a
CLAUDE.md edit, a brand-new skill, or an edit to an existing one — goes through
the `/journal accept` gate. (An earlier version auto-created skills because they
are description-gated; that was changed so you are always asked first — see the
[skill-proposals spec](specs/2026-06-08-skill-proposals-design.md).)

Once you **accept** a new skill, `/journal` writes its `SKILL.md` into the data
repo's `skills/` tree and mirrors it onto the current device; your *other*
devices then pick it up automatically via the SessionStart skill sync — **accept
once, available everywhere.**

## Encryption & trust boundary

```
   YOUR MACHINE (trusted)                    │   GIT HOST + CLOUD (encrypted)
   ───────────────────────────────────────  │  ───────────────────────────────
   ~/.claude/journal/git-crypt.key  (0600)   │   data repo on GitHub: ciphertext
   ~/claude-journal  (unlocked clone)        │   for raw/ digests/ memories/
        │  git-crypt smudge/clean filters    │   skills/ proposals/ state/
        ▼                                     │
   plaintext on disk  ──push──► ciphertext ──┼──► stored encrypted at rest
                                              │
   consolidator (cloud): receives the key via GIT_CRYPT_KEY_B64 in its
   environment, unlocks a fresh clone, works in plaintext in memory, re-encrypts
   on push. The key is never committed and never echoed to logs.
```

- The git-crypt **symmetric key** lives at `~/.claude/journal/git-crypt.key`
  (`chmod 600`), **outside** any repo. It is transferred between devices
  out-of-band (a password manager), never through the repo.
- `tools/journal/encryption.py` cannot decrypt anything — it only *detects* the
  git-crypt magic-byte prefix (`\x00GITCRYPT`) to warn when a repo is locked.
- `consolidator/` is intentionally **not** encrypted so the routine can read its
  own prompt from a fresh, still-locked checkout.

See [../SECURITY.md](../SECURITY.md) for the full security model.

## Data repo layout

```
claude-journal/                      ← your private, git-crypt-encrypted data repo
├── raw/                         🔒  immutable session breadcrumbs (consolidator input)
│   └── <device>/<YYYY-MM-DD>/
│       ├── <session_id>.json        structural breadcrumb
│       └── <session_id>.transcript.md  trimmed transcript
├── digests/                     🔒  per-device daily summaries
│   └── <YYYY-MM-DD>/<device>.md
├── memories/                    🔒  distilled facts (auto-synced to devices)
│   └── <project-key>/
│       ├── MEMORY.md                index of the project's memories
│       └── <slug>.md                one fact per file
├── skills/                      🔒  ACCEPTED skills (synced to devices) + manifest
│   ├── INDEX.md                     status of every proposed/accepted skill
│   ├── global/<name>/SKILL.md       cross-project
│   └── projects/<project>/<name>/SKILL.md   project-scoped
├── proposals/                   🔒  pending behavior changes (need /journal accept)
│   └── <YYYY-MM-DD>-<project-key>.md   feedback · CLAUDE.md edit · new-skill
├── state/                       🔒  per-project CLAUDE.md snapshots (diff source)
│   └── <project-key>/CLAUDE.md
├── consolidator/                    NOT encrypted
│   └── ROUTINE.md                   the nightly routine's prompt (source of truth)
├── .gitattributes                   declares which dirs git-crypt encrypts
├── README.md
└── CHANGELOG.md                     skill lifecycle ledger (~proposed +accepted -skipped)
```

`raw/` is **append-only and immutable** — the consolidator reads it but never
edits or deletes it, so a failed run never loses input. Everything else is
derived from it.
