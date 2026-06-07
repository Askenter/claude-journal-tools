#!/usr/bin/env bash
# First-time creation of a new private claude-journal *data* repo.
# Usage: ./scripts/bootstrap-journal-repo.sh --repo <you>/claude-journal
#        ./scripts/bootstrap-journal-repo.sh --no-remote   # local-only
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${HERE}/venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
exec env PYTHONPATH="${HERE}${PYTHONPATH:+:$PYTHONPATH}" "$PY" -m tools.journal.bootstrap "$@"
