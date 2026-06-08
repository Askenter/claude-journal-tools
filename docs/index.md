# claude-journal — documentation

A personal **cognitive-consolidation pipeline** for Claude Code. It captures a
small breadcrumb from every Claude Code session across all your devices,
distills them nightly into durable **memories, skills, and proposals**, and
propagates the results back to every device — so Claude gets a little better at
*your* work over time without you hand-maintaining context.

It is two git repositories working together:

- **`claude-journal-tools`** — the device-side code you install (this repo): a
  Claude Code *plugin* (Stop + SessionStart hooks) plus three skills.
- **`claude-journal`** — *your own* private, git-crypt-encrypted **data repo**
  that holds the breadcrumbs and everything distilled from them. You create it;
  this tools repo ships no data and no key.

```
   capture            consolidate              propagate
   (per device)       (nightly, cloud)         (per device)
  ┌──────────┐  push  ┌──────────────┐  push  ┌──────────────┐
  │ Stop hook│ ─────► │ data repo    │ ◄─────►│ consolidator │
  │ writes a │        │ (encrypted)  │        │ distills raw │
  │ breadcrumb│       │  raw/ …      │        │ → memories/  │
  └──────────┘        └──────┬───────┘        │   skills/    │
                             │ pull            │   proposals/ │
                             ▼                 └──────────────┘
                      ┌──────────────┐
                      │SessionStart  │  syncs memories + skills onto the
                      │ hook on each │  device, surfaces proposals for you
                      │ device       │  to accept / skip / edit
                      └──────────────┘
```

## The one-paragraph mental model

Every time a Claude Code session ends, a **Stop hook** writes a structural
*breadcrumb* (what files were touched, which skills ran, the first prompt) plus
a trimmed transcript, and pushes them to your encrypted data repo under `raw/`.
Once a night, a single **cloud routine** (the *consolidator*, created with
Claude Code's `/schedule`) reads yesterday's raw breadcrumbs from *all* devices
and distills them into per-day **digests**, per-project **memories**, and
**proposals** (new skills, behavioral rules, and CLAUDE.md edits it is not
allowed to apply on its own). Every time a session *starts*, a **SessionStart
hook** pulls the data repo, mirrors the distilled memories (and any
already-accepted skills) onto that device, and surfaces any pending proposals so
you can `/journal accept|skip|edit` them. Distilled facts flow automatically;
new skills, feedback rules, and CLAUDE.md edits — anything that changes how
Claude *behaves* — wait for your explicit `/journal accept`.

## Documentation map

| Doc | Read it for |
| --- | --- |
| [architecture.md](architecture.md) | The components, the two repos, the three phases, the encryption/trust boundary, and the data-repo layout. **Start here.** |
| [data-flow.md](data-flow.md) | The full life of a breadcrumb — capture → push → consolidate → propagate → proposal — with step-by-step sequence diagrams. |
| [setup.md](setup.md) | Install the plugin, bootstrap the data repo, add devices, schedule the nightly routine, verify, and troubleshoot. |
| [reference.md](reference.md) | Exhaustive reference: env vars, CLI entrypoints, file/repo layout, data formats (breadcrumb, transcript, proposal), hooks, skills. |
| [agents.md](agents.md) | **For AI agents.** How to *use* a project wired into claude-journal: which artifacts to read, which to never read, and how the proposal workflow works. |
| [../SECURITY.md](../SECURITY.md) | The security model: what gets pushed, your responsibilities, encryption, and failure behavior. **Read before installing.** |

## Design principles

- **Capture is dumb, consolidation is smart.** The device hooks run *no* LLM —
  they only collect structured data and sync files. All judgment (what's worth
  remembering, what's a reusable skill) happens in the one nightly cloud step.
- **Facts auto-apply; behavior changes ask first.** Distilled `user`/`project`/
  `reference` memories sync to your devices automatically. Anything that changes
  how Claude *behaves* — new skills, feedback rules, CLAUDE.md edits, edits to
  existing skills — is written as a **proposal** and never applied without your
  `/journal accept`. Once you accept a skill, it then syncs to your other
  devices automatically.
- **Private and encrypted by construction.** The data repo must be private and
  git-crypt-encrypted. The key lives outside any repo and is never committed.
- **Best-effort, never blocking.** Hooks always exit 0. A locked repo, a failed
  push, or no network degrades to a local buffer + a warning — never a lost
  session or an interrupted prompt.
- **Standard library only.** The device code is Python 3.11+ stdlib — no
  `pip install`, no `node_modules`.

## Glossary

- **Breadcrumb** — the small structured JSON record one session produces
  (`session_id`, `device`, `project`, timestamps, `files_touched`,
  `skills_invoked`, `first_prompt`).
- **Data repo** — your private `claude-journal` git repo. Holds `raw/`,
  `digests/`, `memories/`, `skills/`, `proposals/`, `state/`, `consolidator/`.
- **Tools repo** — this repo, `claude-journal-tools`. The installable plugin +
  scripts. Contains no personal data.
- **Consolidator** — the once-per-account nightly Claude Code routine (created
  via `/schedule`) that turns raw breadcrumbs into distilled artifacts.
- **Project key** — an absolute project path slugified by replacing `/` with
  `-` (e.g. `/home/opc/ASEP` → `-home-opc-ASEP`). Used to bucket memories and
  proposals per project.
- **Proposal** — a distilled change that alters Claude's behavior (a feedback
  rule, a CLAUDE.md edit, an edit to an existing skill, or a brand-new skill
  suggestion). Surfaced at SessionStart; applied only via `/journal accept`.
- **Digest** — a per-device, per-day human-readable summary the consolidator
  writes to `digests/<date>/<device>.md`.
