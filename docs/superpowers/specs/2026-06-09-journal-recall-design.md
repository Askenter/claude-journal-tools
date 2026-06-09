# Journal recall — `/journal recall`

Status: approved design, ready for implementation
Date: 2026-06-09

## Problem

The pipeline captures, consolidates, and propagates, but nothing actively
**reads back** the distilled outputs to answer a question. So "what did I do
yesterday" gets reconstructed from raw Claude Code sessions and git history
instead of from the journal's own `digests/`, which exist for exactly that
purpose. The journal is written but not used.

## Goal

A `/journal recall <question>` action that answers from the consolidated
journal. One "ask the journal" skill that routes time questions to `digests/`
and topic questions to `memories/`, reading distilled outputs only, never `raw/`
(the golden rule from `docs/agents.md`).

When a time question lands on a day that has no digest yet (consolidation never
ran for it), the skill **offers** `/journal consolidate` and waits, rather than
auto running it or guessing from raw.

## Non-goals

- Reading or summarizing `raw/` breadcrumbs/transcripts directly.
- Auto running consolidation (the user chose offer-and-wait).
- Natural-language date parsing in Python (Claude resolves the phrase to dates).
- Surfacing proposals or skills (that is `/journal accept|skip|edit`).

## Approach

A thin tested helper plus Claude synthesis, the same split as consolidate's
`plan`/`finalize`. `tools/journal/recall.py` does the mechanical, testable work
(pull, unlock check, enumerate which device digests exist for a set of dates,
detect gaps, list memory files). The current Claude does the judgment (resolve
"yesterday" to a UTC date, read the located files, synthesize the answer).
Time-vs-topic routing lives in the skill prose.

Rejected: a pure-prose skill with no helper (fragile date/device enumeration and
gap detection, untested, breaks the repo's tested-mechanical-steps pattern); and
full-Python synthesis (the synthesis is exactly what the LLM should do).

## Components

### `tools/journal/recall.py` (new, tested, stdlib)

Self-locating entrypoint like the other tools. Reuses `paths.py`, `pull.py`,
`encryption.py`. Reads `digests/` and `memories/` only.

`inventory_dates(repo, dates) -> dict`
For each date: the device digest files that exist
(`digests/<date>/<device>.md`), the devices that have `raw/<device>/<date>/*.json`
but no digest, and a per-date `status`:
- `ok` — every device with raw that date has a digest (fully consolidated).
- `gap` — raw exists for the date but there is no digest at all.
- `partial` — some device digests exist, at least one raw device lacks one.
- `empty` — no raw and no digest (nothing was captured that day).
Plus top-level `gaps` (dates that are `gap` or `partial`, i.e. worth offering
consolidate) and `empty` (dates with no captured activity).

`inventory_memories(repo, project=None) -> dict`
Per project-key: the `MEMORY.md` index path (if present) and the list of memory
files, optionally filtered to one project.

`plan(repo, mode, args)` pulls (best-effort), asserts the repo is unlocked
(aborts with a clear message if locked — never inventory ciphertext), then
dispatches to `inventory_dates` (validating canonical `YYYY-MM-DD` inputs) or
`inventory_memories`, and prints a JSON inventory. CLI forms:
`recall.py dates <YYYY-MM-DD>...` and `recall.py memories [project]`.

### `skills/journal/references/recall.md` (new)

Drives the current Claude:
1. Read the question (the text after `recall`); decide time vs topic.
2. **Time** — resolve the phrase to concrete UTC dates relative to today (run
   `date -u +%F` if unsure), run `recall.py dates <dates…>`, Read the returned
   digest files, and synthesize a concise answer grouped by project. For each
   date in `gaps`, tell the user it isn't consolidated yet and offer
   `/journal consolidate <date>` — wait for go-ahead, do not auto run. For
   `empty` dates, say no activity was captured.
3. **Topic** — run `recall.py memories [project]`, use the `MEMORY.md`
   description lines to pick relevant files, Read them, answer with citations.
4. Golden rule: read `digests/` and `memories/` only, never `raw/`. If a gap
   exists, offer consolidate rather than reading raw.
5. If `plan` reports `locked`, stop and tell the user to
   `git-crypt unlock ~/.claude/journal/git-crypt.key`. If `pull_ok` is false,
   note results may be stale and continue.

### Dispatch (`skills/journal/SKILL.md`)

Add a `recall` row to the action table, the help block, and the frontmatter
description.

## Data flow

`/journal recall what did I do yesterday` → Claude resolves yesterday to
`2026-06-08` (UTC) → `recall.py dates 2026-06-08` → Claude reads
`digests/2026-06-08/<device>.md` across devices → synthesizes the answer. If
that date is a `gap`, it offers `/journal consolidate 2026-06-08` instead of
guessing from raw — the failure mode the journal is meant to prevent, fixed at
the source.

## Errors and guardrails

- Locked repo aborts before any inventory; points at `git-crypt unlock`.
- A failed pull warns that results may be stale but still answers from local
  state.
- Non-canonical date inputs are rejected (`recall.py dates` validates
  `YYYY-MM-DD`).
- `raw/` is never read by the helper or the skill.

## Tests

`tests/journal/test_recall.py`:
- `inventory_dates`: `ok`, `gap`, `partial`, `empty`, and multi-device cases;
  `gaps`/`empty` summaries.
- `inventory_memories`: grouping, project filter, missing `MEMORY.md`, empty.
- `plan`: locked abort, bad-date rejection, dates mode, memories mode.

## Docs

`architecture.md` (the read side of the loop), `data-flow.md` (the recall path),
`reference.md` (module map + skills table), `README.md` (skill list), `index.md`,
`agents.md` (decision flow: asked "what did I do / what do I know" →
`/journal recall`), plus this spec. Bump `plugin.json` to `0.7.0` with a
CHANGELOG entry.
