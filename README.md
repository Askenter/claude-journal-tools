# claude-journal-tools

Code that powers the personal cognitive-consolidation pipeline: per-device
Stop/SessionStart hooks that push session breadcrumbs to the
[claude-journal](https://github.com/askenter/claude-journal) data repo.

Phase 1 (this repo's current scope): structural breadcrumbs only — no
in-hook LLM. The central nightly Anthropic-cloud routine (Phase 2) does
the LLM-driven distillation across all devices' breadcrumbs.

## Layout

```
claude-journal-tools/
├── tools/journal/      hook implementation, breadcrumb model, push/pull, init
├── tests/journal/      pytest suite (stdlib only, ~28 tests)
├── scripts/            init-journal-device.sh
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
