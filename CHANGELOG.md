# Changelog

All notable changes to **claude-journal-tools** (the device-side plugin) are
recorded here. This is the *tools* repo's changelog; your private `claude-journal`
*data* repo keeps its own skill ledger.

The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project aims to follow [Semantic Versioning](https://semver.org/). The
`version` field in `.claude-plugin/plugin.json` is the release marker — bump it
on every release or installed plugins won't see the change.

## [0.3.0] — 2026-06-08

### Added
- **The cloud consolidator now provisions its own GitHub credential.**
  `/journal-setup` gained Step 4b, which walks you through minting a
  fine-grained personal access token (scoped to the data repo, Contents: Read
  and write), stores it at `~/.claude/journal/gh-token` without echoing the
  value, and verifies it authenticates. The token is captured at setup and
  injected into the routine at schedule time.
- **`/journal-schedule` injects `GH_TOKEN`** alongside the git-crypt key and
  clones the private repo over HTTPS with the token
  (`https://x-access-token:$GH_TOKEN@github.com/<owner>/<repo>.git`); the same
  credential authenticates the routine's `git push`. A new precondition
  verifies the token has push access before scheduling.

### Fixed
- **The nightly routine no longer dies at clone in environments with no GitHub
  auth** (Claude Code on the web, headless cloud runs). It previously received
  only `GIT_CRYPT_KEY_B64`, which decrypts contents but is not a transport
  credential, so cloning the **private** data repo failed with `could not read
  Username for github.com` before git-crypt ever ran. A device's local SSH key
  and `gh` login do not propagate to the cloud.

### Security
- The new `GH_TOKEN` and the token embedded in the clone URL get the same
  write-once, never-echo handling as the git-crypt key. `ROUTINE.md` now warns
  against printing `remote.origin.url` (it carries the token) and requires
  scrubbing `https://x-access-token:…@github.com` strings out of any logged
  push error.

## [0.2.2] — 2026-06-08

### Fixed
- **Stop/SessionStart hooks no longer crash on older Python.** `breadcrumb.py`
  and the two hook entrypoints were missing `from __future__ import
  annotations`, so PEP 585 builtin-generic annotations (`list[str]`,
  `dict[str, Any]`) were evaluated at import time and raised `TypeError: 'type'
  object is not subscriptable` on interpreters below 3.9. The annotations are
  now deferred, matching the rest of the package, so the hooks run under
  whatever `python3` is on PATH.

## [0.2.1] — 2026-06-08

### Fixed
- **Plugin install no longer fails with a duplicate-hooks error.** Removed the
  redundant `hooks` field from `.claude-plugin/plugin.json`. The standard
  `hooks/hooks.json` is auto-discovered, so naming it in the manifest loaded the
  same file twice and aborted hook registration at install time. SessionStart
  and Stop hooks now load cleanly via auto-discovery.

## [0.2.0] — 2026-06-08

Turnkey setup, skills-as-proposals, and full documentation.

### Added
- **`/journal-setup` skill** — interactive first-time data-repo bootstrap:
  checks tools, sets your git identity, signs you into `gh` when a remote is
  wanted, then runs the bootstrap with the git-crypt key kept out of the
  transcript.
- **`journal-bootstrap`** (`scripts/bootstrap-journal-repo.sh`) — create a
  private, git-crypt-encrypted data repo from zero (`--repo` or `--no-remote`).
- **`/journal-schedule` skill** — create the once-per-account nightly
  consolidator routine via `/schedule`, idempotently and DST-safe.
- **Skills now flow through the proposal queue.** Net-new skills (Track 2) are
  *proposed* via `/journal accept|skip|edit`, with a `CHANGELOG.md` ledger and a
  `skills/INDEX.md` manifest in the data repo, instead of silently
  auto-applying. Editing existing skills (Track 3) is unchanged.
- **Full consolidator `ROUTINE.md`** shipped as the seeded template.
- **Documentation set under `docs/`** — `index`, `architecture`, `data-flow`,
  `setup`, `reference`, `agents` — built for humans and agents, with ASCII
  diagrams.
- `/journal-setup` now offers to enable plugin **auto-update** during setup, so
  future releases reach the device hands-off.

### Fixed
- Bootstrap validates every precondition (pre-existing key, git identity, `gh`
  auth) **before** any filesystem mutation, so a fresh machine can never end up
  with a half-initialized repo and an orphaned git-crypt key.
- DST-safe schedule-time computation now resolves the IANA timezone on
  macOS/RHEL instead of silently collapsing to a fixed offset.
- Corrected the README update instructions: upgrading the plugin needs both
  `/plugin marketplace update` **and** `/plugin update` (the first alone only
  refreshes the marketplace, it does not install the new version).
- `sync_memories` no longer duplicates a project's `MEMORY.md` index entry on
  every SessionStart when the entry's link text contains parentheses (e.g. a
  `(date)`). The dedupe now keys on the markdown link **target** (`](file.md)`)
  rather than the first parenthetical, which was matching the title's date and
  never the filename — appending one duplicate per sync.

### Changed
- Skills are referenced by their bare names (`/journal`, `/journal-setup`,
  `/journal-schedule`) throughout the docs and skill cross-references.

## [0.1.0] — initial

First packaged release of the Phase 1 + Phase 3 pipeline.

### Added
- **Phase 1 capture** — a `Stop` hook writes a structural breadcrumb plus a
  tail-truncated, secret-redacted transcript and pushes them to the encrypted
  data repo under `raw/`, with an offline buffer + drain on failure.
- **Phase 3 propagation** — a `SessionStart` hook pulls the data repo, mirrors
  consolidated memories and skills onto the device, and surfaces pending
  proposals as `additionalContext`.
- **`/journal` skill** — resolve pending proposals with `accept` / `skip` /
  `edit`.
- Project `CLAUDE.md` snapshotting into `state/` (Track 3 diff source).
- Lock detection + a SessionStart warning when the data repo is git-crypt-locked;
  `STALE_REPO_WARNING` when the pull fails.
- git-crypt keyfile base64 redaction from pushed transcripts.
- pull/push hooks robust to a dirty working tree; commit-before-pull so a
  re-fired `Stop` never wedges future pushes.
- Packaged as a Claude Code plugin with a marketplace manifest.
