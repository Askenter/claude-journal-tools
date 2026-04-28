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
- records the device name at `~/.claude/journal/device-name`
- symlinks hook entrypoints into `~/.claude/hooks/`
- registers them under Stop and SessionStart in `~/.claude/settings.json`

Re-running the script is safe (idempotent).
